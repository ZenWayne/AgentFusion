-- ================================================
-- AgentFusion Prompt Version Management Database
-- ================================================

-- Drop existing tables if they exist (for recreation)
DROP TABLE IF EXISTS feedbacks CASCADE;
DROP TABLE IF EXISTS elements CASCADE;
DROP TABLE IF EXISTS steps CASCADE;
DROP TABLE IF EXISTS threads CASCADE;
DROP TABLE IF EXISTS user_activity_logs CASCADE;
DROP TABLE IF EXISTS user_api_keys CASCADE;
DROP TABLE IF EXISTS user_preferences CASCADE;
DROP TABLE IF EXISTS user_sessions CASCADE;
DROP TABLE IF EXISTS password_reset_tokens CASCADE;
DROP TABLE IF EXISTS prompt_change_history CASCADE;
DROP TABLE IF EXISTS prompt_versions CASCADE;
DROP TABLE IF EXISTS prompts CASCADE;
DROP TABLE IF EXISTS group_chat_participants CASCADE;
DROP TABLE IF EXISTS group_chats CASCADE;
DROP TABLE IF EXISTS agent_mcp_servers CASCADE;
DROP TABLE IF EXISTS mcp_servers CASCADE;
DROP TABLE IF EXISTS agents CASCADE;
DROP TABLE IF EXISTS model_clients CASCADE;
DROP TABLE IF EXISTS component_types CASCADE;
DROP TABLE IF EXISTS "User" CASCADE;

-- ================================================
-- Core Tables
-- ================================================

-- Component types lookup table
CREATE TABLE component_types (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL UNIQUE,
    description TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Users table
CREATE TABLE "User" (
    id SERIAL PRIMARY KEY,
    user_uuid UUID UNIQUE DEFAULT gen_random_uuid(), -- External identifier
    username VARCHAR(100) NOT NULL UNIQUE,
    identifier VARCHAR(100) NOT NULL UNIQUE, -- For Chainlit compatibility
    email VARCHAR(255) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    first_name VARCHAR(100),
    last_name VARCHAR(100),
    role VARCHAR(50) DEFAULT 'user', -- user, admin, reviewer, developer
    is_active BOOLEAN DEFAULT TRUE,
    is_verified BOOLEAN DEFAULT FALSE,
    avatar_url VARCHAR(500),
    timezone VARCHAR(50) DEFAULT 'UTC',
    language VARCHAR(10) DEFAULT 'en',
    last_login TIMESTAMP,
    failed_login_attempts INTEGER DEFAULT 0,
    locked_until TIMESTAMP,
    email_verified_at TIMESTAMP,
    phone VARCHAR(20),
    user_metadata JSONB DEFAULT '{}', -- Store additional user preferences, settings, etc.
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_by INTEGER REFERENCES "User"(id),
    CONSTRAINT check_role CHECK (role IN ('user', 'admin', 'reviewer', 'developer', 'system'))
);

-- Password reset tokens table
CREATE TABLE password_reset_tokens (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES "User"(id) ON DELETE CASCADE,
    token VARCHAR(255) NOT NULL UNIQUE,
    token_hash VARCHAR(255) NOT NULL, -- Store hashed version for security
    expires_at TIMESTAMP NOT NULL,
    used_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    ip_address INET,
    user_agent TEXT
);

-- User sessions table
CREATE TABLE user_sessions (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES "User"(id) ON DELETE CASCADE,
    session_token VARCHAR(255) NOT NULL UNIQUE,
    refresh_token VARCHAR(255),
    ip_address INET,
    user_agent TEXT,
    device_info JSONB DEFAULT '{}',
    location_info JSONB DEFAULT '{}', -- Country, city, etc.
    is_active BOOLEAN DEFAULT TRUE,
    last_activity TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- User preferences table
CREATE TABLE user_preferences (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES "User"(id) ON DELETE CASCADE,
    preference_key VARCHAR(100) NOT NULL,
    preference_value JSONB NOT NULL,
    category VARCHAR(50) DEFAULT 'general', -- ui, notification, security, etc.
    description TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, preference_key)
);

-- User API keys table
CREATE TABLE user_api_keys (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES "User"(id) ON DELETE CASCADE,
    name VARCHAR(100) NOT NULL, -- User-friendly name for the key
    key_prefix VARCHAR(20) NOT NULL, -- First few chars for identification
    key_hash VARCHAR(255) NOT NULL, -- Hashed API key
    permissions JSONB DEFAULT '{}', -- Specific permissions for this key
    rate_limit INTEGER DEFAULT 1000, -- Requests per hour
    is_active BOOLEAN DEFAULT TRUE,
    last_used TIMESTAMP,
    usage_count INTEGER DEFAULT 0,
    expires_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    ip_whitelist TEXT[], -- Array of allowed IP addresses
    UNIQUE(user_id, name)
);

-- User activity logs table
CREATE TABLE user_activity_logs (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES "User"(id) ON DELETE SET NULL,
    activity_type VARCHAR(50) NOT NULL, -- login, logout, create, update, delete, etc.
    resource_type VARCHAR(50), -- agent, prompt, model_client, etc.
    resource_id INTEGER, -- ID of the affected resource
    action_details JSONB DEFAULT '{}', -- Detailed information about the action
    ip_address INET,
    user_agent TEXT,
    session_id INTEGER REFERENCES user_sessions(id) ON DELETE SET NULL,
    api_key_id INTEGER REFERENCES user_api_keys(id) ON DELETE SET NULL,
    status VARCHAR(20) DEFAULT 'success', -- success, failure, error
    error_message TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Threads table (for conversation/chat management)
CREATE TABLE threads (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT,
    user_id INTEGER NOT NULL REFERENCES "User"(id) ON DELETE CASCADE,
    user_identifier TEXT, -- Legacy compatibility field
    tags TEXT[],
    thread_metadata JSONB DEFAULT '{}',
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    deleted_at TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Steps table (for conversation steps/messages)
CREATE TABLE steps (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL,
    type TEXT NOT NULL, -- message, tool_call, system, etc.
    thread_id UUID NOT NULL REFERENCES threads(id) ON DELETE CASCADE,
    parent_id UUID REFERENCES steps(id) ON DELETE SET NULL,
    streaming BOOLEAN NOT NULL DEFAULT FALSE,
    wait_for_answer BOOLEAN DEFAULT FALSE,
    is_error BOOLEAN DEFAULT FALSE,
    step_metadata JSONB DEFAULT '{}',
    tags TEXT[],
    input TEXT,
    output TEXT,
    command TEXT,
    start_time TIMESTAMP,
    end_time TIMESTAMP,
    generation JSONB DEFAULT '{}', -- AI generation metadata
    show_input TEXT,
    language TEXT,
    indent INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Elements table (for files, images, and other attachments)
CREATE TABLE elements (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    thread_id UUID REFERENCES threads(id) ON DELETE CASCADE,
    step_id UUID REFERENCES steps(id) ON DELETE CASCADE, -- Link to specific step
    type TEXT NOT NULL, -- file, image, text, audio, video, etc.
    url TEXT,
    chainlit_key TEXT, -- For Chainlit compatibility
    name TEXT NOT NULL,
    display TEXT, -- Display mode (inline, side, etc.)
    object_key TEXT, -- Storage object key
    size_bytes BIGINT,
    page_number INTEGER,
    language TEXT,
    for_id UUID, -- Reference to related element
    mime_type TEXT,
    element_metadata JSONB DEFAULT '{}',
    props JSONB DEFAULT '{}',
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Feedbacks table (for user feedback on responses)
CREATE TABLE feedbacks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    for_id UUID NOT NULL, -- Can reference steps, elements, etc.
    thread_id UUID NOT NULL REFERENCES threads(id) ON DELETE CASCADE,
    user_id INTEGER REFERENCES "User"(id) ON DELETE SET NULL,
    value INTEGER NOT NULL, -- Rating value (e.g., 1-5, -1/1, etc.)
    comment TEXT,
    feedback_type VARCHAR(50) DEFAULT 'rating', -- rating, thumbs, stars, etc.
    feedback_metadata JSONB DEFAULT '{}',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Model clients table
CREATE TABLE model_clients (
    id SERIAL PRIMARY KEY,
    client_uuid UUID UNIQUE DEFAULT gen_random_uuid(), -- External identifier
    label VARCHAR(255) NOT NULL UNIQUE,
    provider VARCHAR(500) NOT NULL,
    component_type_id INTEGER REFERENCES component_types(id),
    version INTEGER DEFAULT 1,
    component_version INTEGER DEFAULT 1,
    description TEXT,
    model_name VARCHAR(255),
    base_url VARCHAR(500),
    api_key_hash VARCHAR(255), -- Store hash instead of actual key
    model_info JSONB DEFAULT '{}', -- Store model capabilities (vision, function_calling, etc.)
    config JSONB DEFAULT '{}', -- Store full configuration
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_by INTEGER REFERENCES "User"(id),
    updated_by INTEGER REFERENCES "User"(id),
    is_active BOOLEAN DEFAULT TRUE
);

-- Agents table
CREATE TABLE agents (
    id SERIAL PRIMARY KEY,
    agent_uuid UUID UNIQUE DEFAULT gen_random_uuid(), -- External identifier
    name VARCHAR(255) NOT NULL UNIQUE,
    label VARCHAR(255) NOT NULL,
    provider VARCHAR(500) NOT NULL,
    component_type_id INTEGER REFERENCES component_types(id),
    version INTEGER DEFAULT 1,
    component_version INTEGER DEFAULT 1,
    description TEXT,
    model_client_id INTEGER REFERENCES model_clients(id),
    agent_type VARCHAR(50) DEFAULT 'assistant_agent',
    labels TEXT[] DEFAULT '{}',
    input_func VARCHAR(50) DEFAULT 'input',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_by INTEGER REFERENCES "User"(id),
    updated_by INTEGER REFERENCES "User"(id),
    is_active BOOLEAN DEFAULT TRUE
);

-- Group chats table
CREATE TABLE group_chats (
    id SERIAL PRIMARY KEY,
    group_chat_uuid UUID UNIQUE DEFAULT gen_random_uuid(), -- External identifier
    name VARCHAR(255) NOT NULL UNIQUE,
    type VARCHAR(100) NOT NULL, -- e.g., 'selector_group_chat'
    description TEXT,
    labels TEXT[] DEFAULT '{}', -- Array of labels
    selector_prompt TEXT, -- For selector group chat
    handoff_target VARCHAR(255) DEFAULT 'user', -- For round robin group chat
    termination_condition VARCHAR(255) DEFAULT 'handoff', -- For round robin group chat
    model_client VARCHAR(255), -- Reference to model client label
    component_type_id INTEGER REFERENCES component_types(id),
    version INTEGER DEFAULT 1,
    component_version INTEGER DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_by INTEGER REFERENCES "User"(id),
    updated_by INTEGER REFERENCES "User"(id),
    is_active BOOLEAN DEFAULT TRUE
);

-- MCP (Model Context Protocol) servers table
CREATE TABLE mcp_servers (
    id SERIAL PRIMARY KEY,
    server_uuid UUID UNIQUE DEFAULT gen_random_uuid(), -- External identifier
    name VARCHAR(255) NOT NULL UNIQUE,
    command VARCHAR(500) NOT NULL,
    args JSONB DEFAULT '[]', -- Array of command arguments
    env JSONB DEFAULT '{}', -- Environment variables
    url VARCHAR(500), -- Optional URL for server
    headers JSONB DEFAULT '{}', -- HTTP headers for connection
    timeout INTEGER DEFAULT 30, -- Connection timeout in seconds
    sse_read_timeout INTEGER DEFAULT 30, -- SSE read timeout in seconds
    description TEXT,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_by INTEGER REFERENCES "User"(id),
    updated_by INTEGER REFERENCES "User"(id)
);

-- Agent-MCP Server relationship table (many-to-many)
CREATE TABLE agent_mcp_servers (
    id SERIAL PRIMARY KEY,
    agent_id INTEGER NOT NULL REFERENCES agents(id) ON DELETE CASCADE,
    mcp_server_id INTEGER NOT NULL REFERENCES mcp_servers(id) ON DELETE CASCADE,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_by INTEGER REFERENCES "User"(id),
    UNIQUE(agent_id, mcp_server_id)
);

-- Group chat participants relationship table (many-to-many)
CREATE TABLE group_chat_participants (
    id SERIAL PRIMARY KEY,
    group_chat_id INTEGER NOT NULL REFERENCES group_chats(id) ON DELETE CASCADE,
    agent_id INTEGER NOT NULL REFERENCES agents(id) ON DELETE CASCADE,
    participant_role VARCHAR(100) DEFAULT 'participant', -- participant, moderator, observer
    join_order INTEGER DEFAULT 0, -- Order in which participants join
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_by INTEGER REFERENCES "User"(id),
    UNIQUE(group_chat_id, agent_id)
);

-- Prompts table (main prompt definitions)
CREATE TABLE prompts (
    id SERIAL PRIMARY KEY,
    prompt_uuid UUID UNIQUE DEFAULT gen_random_uuid(), -- External identifier
    prompt_id VARCHAR(100) NOT NULL UNIQUE, -- Business identifier
    name VARCHAR(255) NOT NULL,
    category VARCHAR(100), -- e.g., 'agent', 'group_chat', 'graph_flow'
    subcategories TEXT[] DEFAULT '{}', -- e.g., 'prd_pt', 'ui_designer_pt'
    description TEXT,
    agent_id INTEGER REFERENCES agents(id),
    group_chat_id INTEGER REFERENCES group_chats(id),
    created_by INTEGER REFERENCES "User"(id),
    updated_by INTEGER REFERENCES "User"(id),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    is_active BOOLEAN DEFAULT TRUE
);

-- Prompt versions table (version history)
CREATE TABLE prompt_versions (
    id SERIAL PRIMARY KEY,
    version_uuid UUID UNIQUE DEFAULT gen_random_uuid(), -- External identifier
    prompt_id INTEGER REFERENCES prompts(id),
    version_number INTEGER NOT NULL,
    version_label VARCHAR(100), -- e.g., 'v1.0', 'v1.1-beta'
    content TEXT NOT NULL, -- The actual prompt text
    content_hash VARCHAR(64), -- SHA256 hash of content for integrity
    --CR 这个字段改成prompt_metadata，并修改orm table，包括相关联的所有方法
    metadata JSONB DEFAULT '{}', -- Store template variables, parameters, etc.
    status VARCHAR(50) DEFAULT 'draft', -- draft, review, approved, deprecated
    created_by INTEGER REFERENCES "User"(id),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    approved_by INTEGER REFERENCES "User"(id),
    approved_at TIMESTAMP,
    is_current BOOLEAN DEFAULT FALSE,
    UNIQUE(prompt_id, version_number)
);

-- Prompt change history table (detailed change tracking)
CREATE TABLE prompt_change_history (
    id SERIAL PRIMARY KEY,
    prompt_version_id INTEGER REFERENCES prompt_versions(id),
    change_type VARCHAR(50) NOT NULL, -- 'created', 'updated', 'approved', 'deprecated'
    change_description TEXT,
    old_content TEXT, -- Previous content (for updates)
    new_content TEXT, -- New content (for updates)
    diff_info JSONB DEFAULT '{}', -- Store detailed diff information
    changed_by INTEGER REFERENCES "User"(id),
    changed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    change_reason TEXT,
    metadata JSONB DEFAULT '{}' -- Additional change context
);

-- ================================================
-- Indexes for Performance
-- ================================================

-- Users indexes
CREATE INDEX idx_users_user_uuid ON "User"(user_uuid);
CREATE INDEX idx_users_username ON "User"(username);
CREATE INDEX idx_users_identifier ON "User"(identifier);
CREATE INDEX idx_users_email ON "User"(email);
CREATE INDEX idx_users_role ON "User"(role);
CREATE INDEX idx_users_active ON "User"(is_active);
CREATE INDEX idx_users_created_at ON "User"(created_at);
CREATE INDEX idx_users_timezone ON "User"(timezone);
CREATE INDEX idx_users_language ON "User"(language);

-- Password reset tokens indexes
CREATE INDEX idx_password_reset_tokens_user_id ON password_reset_tokens(user_id);
CREATE INDEX idx_password_reset_tokens_token ON password_reset_tokens(token);
CREATE INDEX idx_password_reset_tokens_expires_at ON password_reset_tokens(expires_at);
CREATE INDEX idx_password_reset_tokens_created_at ON password_reset_tokens(created_at);

-- User sessions indexes
CREATE INDEX idx_user_sessions_user_id ON user_sessions(user_id);
CREATE INDEX idx_user_sessions_session_token ON user_sessions(session_token);
CREATE INDEX idx_user_sessions_is_active ON user_sessions(is_active);
CREATE INDEX idx_user_sessions_expires_at ON user_sessions(expires_at);
CREATE INDEX idx_user_sessions_last_activity ON user_sessions(last_activity);
CREATE INDEX idx_user_sessions_ip_address ON user_sessions(ip_address);

-- User preferences indexes
CREATE INDEX idx_user_preferences_user_id ON user_preferences(user_id);
CREATE INDEX idx_user_preferences_category ON user_preferences(category);
CREATE INDEX idx_user_preferences_key ON user_preferences(preference_key);

-- User API keys indexes
CREATE INDEX idx_user_api_keys_user_id ON user_api_keys(user_id);
CREATE INDEX idx_user_api_keys_key_prefix ON user_api_keys(key_prefix);
CREATE INDEX idx_user_api_keys_is_active ON user_api_keys(is_active);
CREATE INDEX idx_user_api_keys_expires_at ON user_api_keys(expires_at);
CREATE INDEX idx_user_api_keys_last_used ON user_api_keys(last_used);

-- User activity logs indexes
CREATE INDEX idx_user_activity_logs_user_id ON user_activity_logs(user_id);
CREATE INDEX idx_user_activity_logs_activity_type ON user_activity_logs(activity_type);
CREATE INDEX idx_user_activity_logs_resource_type ON user_activity_logs(resource_type);
CREATE INDEX idx_user_activity_logs_created_at ON user_activity_logs(created_at);
CREATE INDEX idx_user_activity_logs_status ON user_activity_logs(status);
CREATE INDEX idx_user_activity_logs_session_id ON user_activity_logs(session_id);
CREATE INDEX idx_user_activity_logs_api_key_id ON user_activity_logs(api_key_id);

-- Threads indexes
CREATE INDEX idx_threads_user_id ON threads(user_id);
CREATE INDEX idx_threads_user_identifier ON threads(user_identifier);
CREATE INDEX idx_threads_is_active ON threads(is_active);
CREATE INDEX idx_threads_created_at ON threads(created_at);
CREATE INDEX idx_threads_updated_at ON threads(updated_at);
CREATE INDEX idx_threads_tags ON threads USING GIN(tags);

-- Steps indexes
CREATE INDEX idx_steps_thread_id ON steps(thread_id);
CREATE INDEX idx_steps_parent_id ON steps(parent_id);
CREATE INDEX idx_steps_type ON steps(type);
CREATE INDEX idx_steps_created_at ON steps(created_at);
CREATE INDEX idx_steps_is_error ON steps(is_error);
CREATE INDEX idx_steps_tags ON steps USING GIN(tags);
CREATE INDEX idx_steps_name ON steps(name);

-- Elements indexes
CREATE INDEX idx_elements_thread_id ON elements(thread_id);
CREATE INDEX idx_elements_step_id ON elements(step_id);
CREATE INDEX idx_elements_type ON elements(type);
CREATE INDEX idx_elements_for_id ON elements(for_id);
CREATE INDEX idx_elements_chainlit_key ON elements(chainlit_key);
CREATE INDEX idx_elements_is_active ON elements(is_active);
CREATE INDEX idx_elements_mime_type ON elements(mime_type);
CREATE INDEX idx_elements_created_at ON elements(created_at);

-- Feedbacks indexes
CREATE INDEX idx_feedbacks_for_id ON feedbacks(for_id);
CREATE INDEX idx_feedbacks_thread_id ON feedbacks(thread_id);
CREATE INDEX idx_feedbacks_user_id ON feedbacks(user_id);
CREATE INDEX idx_feedbacks_value ON feedbacks(value);
CREATE INDEX idx_feedbacks_feedback_type ON feedbacks(feedback_type);
CREATE INDEX idx_feedbacks_created_at ON feedbacks(created_at);

-- Model clients indexes
CREATE INDEX idx_model_clients_client_uuid ON model_clients(client_uuid);

-- Agents indexes
CREATE INDEX idx_agents_agent_uuid ON agents(agent_uuid);
CREATE INDEX idx_agents_name ON agents(name);
CREATE INDEX idx_agents_label ON agents(label);
CREATE INDEX idx_agents_active ON agents(is_active);
CREATE INDEX idx_agents_model_client ON agents(model_client_id);

-- Group chats indexes
CREATE INDEX idx_group_chats_group_chat_uuid ON group_chats(group_chat_uuid);
CREATE INDEX idx_group_chats_name ON group_chats(name);
CREATE INDEX idx_group_chats_type ON group_chats(type);
CREATE INDEX idx_group_chats_active ON group_chats(is_active);

-- Group chat participants indexes
CREATE INDEX idx_group_chat_participants_group_chat_id ON group_chat_participants(group_chat_id);
CREATE INDEX idx_group_chat_participants_agent_id ON group_chat_participants(agent_id);
CREATE INDEX idx_group_chat_participants_active ON group_chat_participants(is_active);

-- MCP servers indexes
CREATE INDEX idx_mcp_servers_server_uuid ON mcp_servers(server_uuid);
CREATE INDEX idx_mcp_servers_name ON mcp_servers(name);
CREATE INDEX idx_mcp_servers_active ON mcp_servers(is_active);

-- Agent-MCP Server relationship indexes
CREATE INDEX idx_agent_mcp_servers_agent_id ON agent_mcp_servers(agent_id);
CREATE INDEX idx_agent_mcp_servers_mcp_server_id ON agent_mcp_servers(mcp_server_id);
CREATE INDEX idx_agent_mcp_servers_active ON agent_mcp_servers(is_active);

-- Prompts indexes
CREATE INDEX idx_prompts_prompt_uuid ON prompts(prompt_uuid);
CREATE INDEX idx_prompts_prompt_id ON prompts(prompt_id);
CREATE INDEX idx_prompts_category ON prompts(category);
CREATE INDEX idx_prompts_agent_id ON prompts(agent_id);
CREATE INDEX idx_prompts_active ON prompts(is_active);

-- Prompt versions indexes
CREATE INDEX idx_prompt_versions_version_uuid ON prompt_versions(version_uuid);
CREATE INDEX idx_prompt_versions_prompt_id ON prompt_versions(prompt_id);
CREATE INDEX idx_prompt_versions_version ON prompt_versions(version_number);
CREATE INDEX idx_prompt_versions_current ON prompt_versions(is_current);
CREATE INDEX idx_prompt_versions_status ON prompt_versions(status);
CREATE INDEX idx_prompt_versions_created_at ON prompt_versions(created_at);

-- Change history indexes
CREATE INDEX idx_change_history_prompt_version ON prompt_change_history(prompt_version_id);
CREATE INDEX idx_change_history_change_type ON prompt_change_history(change_type);
CREATE INDEX idx_change_history_changed_at ON prompt_change_history(changed_at);
CREATE INDEX idx_change_history_changed_by ON prompt_change_history(changed_by);

-- ================================================
-- Triggers for Automatic Updates
-- ================================================

-- Function to update the updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Triggers for updated_at
CREATE TRIGGER update_users_updated_at BEFORE UPDATE ON "User" FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
CREATE TRIGGER update_user_preferences_updated_at BEFORE UPDATE ON user_preferences FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
CREATE TRIGGER update_user_api_keys_updated_at BEFORE UPDATE ON user_api_keys FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
CREATE TRIGGER update_threads_updated_at BEFORE UPDATE ON threads FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
CREATE TRIGGER update_steps_updated_at BEFORE UPDATE ON steps FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
CREATE TRIGGER update_elements_updated_at BEFORE UPDATE ON elements FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
CREATE TRIGGER update_feedbacks_updated_at BEFORE UPDATE ON feedbacks FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
CREATE TRIGGER update_agents_updated_at BEFORE UPDATE ON agents FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
CREATE TRIGGER update_group_chats_updated_at BEFORE UPDATE ON group_chats FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
CREATE TRIGGER update_prompts_updated_at BEFORE UPDATE ON prompts FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
CREATE TRIGGER update_model_clients_updated_at BEFORE UPDATE ON model_clients FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
CREATE TRIGGER update_mcp_servers_updated_at BEFORE UPDATE ON mcp_servers FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- Function to ensure only one current version per prompt
CREATE OR REPLACE FUNCTION ensure_single_current_version()
RETURNS TRIGGER AS $$
BEGIN
    IF NEW.is_current = TRUE THEN
        -- Set all other versions of this prompt to non-current
        UPDATE prompt_versions 
        SET is_current = FALSE 
        WHERE prompt_id = NEW.prompt_id AND id != NEW.id;
    END IF;
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Trigger to ensure single current version
CREATE TRIGGER ensure_single_current_version_trigger 
    BEFORE INSERT OR UPDATE ON prompt_versions 
    FOR EACH ROW EXECUTE FUNCTION ensure_single_current_version();

-- Function to log changes to prompt_change_history
CREATE OR REPLACE FUNCTION log_prompt_changes()
RETURNS TRIGGER AS $$
BEGIN
    IF TG_OP = 'INSERT' THEN
        INSERT INTO prompt_change_history (
            prompt_version_id, change_type, change_description, 
            new_content, changed_by, changed_at
        ) VALUES (
            NEW.id, 'created', 'New prompt version created',
            NEW.content, NEW.created_by, NEW.created_at
        );
        RETURN NEW;
    ELSIF TG_OP = 'UPDATE' THEN
        -- Log content changes
        IF OLD.content != NEW.content THEN
            INSERT INTO prompt_change_history (
                prompt_version_id, change_type, change_description,
                old_content, new_content, changed_by, changed_at
            ) VALUES (
                NEW.id, 'updated', 'Prompt content updated',
                OLD.content, NEW.content, NEW.created_by, CURRENT_TIMESTAMP
            );
        END IF;
        
        -- Log status changes
        IF OLD.status != NEW.status THEN
            INSERT INTO prompt_change_history (
                prompt_version_id, change_type, change_description,
                changed_by, changed_at, change_reason
            ) VALUES (
                NEW.id, 'status_changed', 
                'Status changed from ' || OLD.status || ' to ' || NEW.status,
                NEW.approved_by, CURRENT_TIMESTAMP, 
                'Status update'
            );
        END IF;
        
        RETURN NEW;
    END IF;
    RETURN NULL;
END;
$$ language 'plpgsql';

-- Trigger to log changes
CREATE TRIGGER log_prompt_changes_trigger 
    AFTER INSERT OR UPDATE ON prompt_versions 
    FOR EACH ROW EXECUTE FUNCTION log_prompt_changes();

-- Function to auto-log user activity for critical actions
CREATE OR REPLACE FUNCTION auto_log_user_activity()
RETURNS TRIGGER AS $$
BEGIN
    -- Log creation of new agents
    IF TG_TABLE_NAME = 'agents' AND TG_OP = 'INSERT' THEN
        PERFORM log_user_activity(
            NEW.created_by, 'create', 'agent', NEW.id,
            jsonb_build_object('name', NEW.name, 'label', NEW.label),
            NULL, NULL, NULL, NULL, 'success', NULL
        );
    END IF;
    
    -- Log creation of new prompts
    IF TG_TABLE_NAME = 'prompts' AND TG_OP = 'INSERT' THEN
        PERFORM log_user_activity(
            NEW.created_by, 'create', 'prompt', NEW.id,
            jsonb_build_object('prompt_id', NEW.prompt_id, 'name', NEW.name),
            NULL, NULL, NULL, NULL, 'success', NULL
        );
    END IF;
    
    -- Log creation of new model clients
    IF TG_TABLE_NAME = 'model_clients' AND TG_OP = 'INSERT' THEN
        PERFORM log_user_activity(
            NEW.created_by, 'create', 'model_client', NEW.id,
            jsonb_build_object('label', NEW.label, 'model_name', NEW.model_name),
            NULL, NULL, NULL, NULL, 'success', NULL
        );
    END IF;
    
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Triggers for automatic activity logging
CREATE TRIGGER auto_log_agent_activity 
    AFTER INSERT ON agents 
    FOR EACH ROW EXECUTE FUNCTION auto_log_user_activity();

CREATE TRIGGER auto_log_prompt_activity 
    AFTER INSERT ON prompts 
    FOR EACH ROW EXECUTE FUNCTION auto_log_user_activity();

CREATE TRIGGER auto_log_model_client_activity 
    AFTER INSERT ON model_clients 
    FOR EACH ROW EXECUTE FUNCTION auto_log_user_activity();

-- ================================================
-- Initial Data Population
-- ================================================

-- Insert system user first (for self-referencing foreign key)
INSERT INTO "User" (username, identifier, email, password_hash, first_name, last_name, role, is_active, is_verified) VALUES 
    ('system', 'system', 'system@agentfusion.local', '$2b$12$dummy_hash_for_system_user', 'System', 'User', 'system', TRUE, TRUE);

-- Insert sample users
INSERT INTO "User" (username, identifier, email, password_hash, first_name, last_name, role, is_active, is_verified, email_verified_at, timezone, language, created_by) VALUES 
    ('admin', 'admin', 'admin@agentfusion.local', '$2b$12$u7aV8xnkMhUZuj9qh1QoauZp4JIF1Aa4s1kWclyCZzVyhmyugzCNW', 'Admin', 'User', 'admin', TRUE, TRUE, CURRENT_TIMESTAMP, 'UTC', 'en', 1),
    ('developer', 'developer', 'dev@agentfusion.local', '$2b$12$u7aV8xnkMhUZuj9qh1QoauZp4JIF1Aa4s1kWclyCZzVyhmyugzCNW', 'Developer', 'User', 'developer', TRUE, TRUE, CURRENT_TIMESTAMP, 'UTC', 'en', 1),
    ('reviewer', 'reviewer', 'reviewer@agentfusion.local', '$2b$12$u7aV8xnkMhUZuj9qh1QoauZp4JIF1Aa4s1kWclyCZzVyhmyugzCNW', 'Reviewer', 'User', 'reviewer', TRUE, TRUE, CURRENT_TIMESTAMP, 'UTC', 'en', 1);

-- Insert sample user preferences
INSERT INTO user_preferences (user_id, preference_key, preference_value, category, description) VALUES 
    (2, 'theme', '"dark"', 'ui', 'User interface theme preference'),
    (2, 'auto_save', 'true', 'editor', 'Auto-save prompt changes'),
    (2, 'notification_email', 'true', 'notification', 'Receive email notifications'),
    (3, 'theme', '"light"', 'ui', 'User interface theme preference'),
    (3, 'items_per_page', '25', 'ui', 'Number of items to display per page'),
    (4, 'language', '"zh"', 'ui', 'Preferred interface language');

-- Insert sample API keys
INSERT INTO user_api_keys (user_id, name, key_prefix, key_hash, permissions, rate_limit, is_active) VALUES 
    (2, 'Development API Key', 'af_dev_', '$2b$12$sample_hashed_api_key_for_development', '{"read": true, "write": true, "admin": false}', 2000, TRUE),
    (3, 'Review API Key', 'af_rev_', '$2b$12$sample_hashed_api_key_for_review', '{"read": true, "write": false, "admin": false}', 1000, TRUE);

-- Insert component types
INSERT INTO component_types (name, description) VALUES 
    ('agent', 'AI Agent component'),
    ('model', 'Model client component'),
    ('team', 'Group chat team component'),
    ('termination', 'Termination condition component'),
    ('chat_completion_context', 'Chat completion context component');

-- Insert sample model clients based on the config
INSERT INTO model_clients (label, provider, component_type_id, description, model_name, base_url, model_info, created_by) VALUES 
    ('deepseek-chat_DeepSeek', 'autogen_ext.models.openai.OpenAIChatCompletionClient', 2, 'Chat completion client for OpenAI hosted models.', 'deepseek-chat', 'https://api.deepseek.com/v1', 
     '{"vision": false, "function_calling": true, "json_output": true, "family": "r1"}'::jsonb, 1),
     ('qwq-32b_Aliyun', 'autogen_ext.models.openai.OpenAIChatCompletionClient', 2, 'Chat completion client for OpenAI hosted models.', 'qwq-32b', 'https://dashscope.aliyuncs.com/compatible-mode/v1', 
     '{"vision": false, "function_calling": true, "json_output": true, "family": "r1"}'::jsonb, 1);

-- Insert sample agents
INSERT INTO agents (name, label, provider, component_type_id, description, model_client_id, agent_type, labels, input_func, created_by) VALUES 
    ('prompt_refiner', 'prompt_refiner', 'autogen_agentchat.agents.AssistantAgent', 1, 'An agent that provides assistance with tool use.', 1, 'assistant_agent', ARRAY['prompt', 'refiner'], 'input', 1),
    ('executor', 'executor', 'autogen_agentchat.agents.AssistantAgent', 1, 'An agent that provides assistance with tool use.', 1, 'assistant_agent', ARRAY['executor', 'action'], 'input', 1),
    ('user', 'UserProxyAgent', 'autogen_agentchat.agents.UserProxyAgent', 1, 'A human user', 1, 'user_proxy_agent', ARRAY['user', 'proxy'], 'input', 1);

-- Insert sample MCP servers based on config.json
INSERT INTO mcp_servers (name, command, args, env, url, timeout, sse_read_timeout, description, created_by) VALUES 
    ('file_system_windows', 'node', 
     '["${userHome}\\\\AppData\\\\Roaming\\\\npm\\\\node_modules\\\\@modelcontextprotocol\\\\server-filesystem\\\\dist\\\\index.js", "${cwd}"]'::jsonb, 
     '{}'::jsonb, NULL, 30, 30, 'File system MCP server for Windows', 1),
    ('file_system_unix', 'npx', 
     '["@modelcontextprotocol/server-filesystem", "${cwd}"]'::jsonb, 
     '{}'::jsonb, NULL, 30, 30, 'File system MCP server for Unix/Linux', 1),
    ('file_system', 'node', 
     '["${userHome}\\\\AppData\\\\Roaming\\\\npm\\\\node_modules\\\\@modelcontextprotocol\\\\server-filesystem\\\\dist\\\\index.js", "${cwd}"]'::jsonb, 
     '{}'::jsonb, NULL, 10, 10, 'Default file system MCP server', 1);

-- Insert sample agent-MCP server relationships
INSERT INTO agent_mcp_servers (agent_id, mcp_server_id, created_by) VALUES 
    (1, 1, 1), -- prompt_refiner uses file_system_windows
    (1, 3, 1), -- prompt_refiner uses file_system
    (2, 1, 1), -- executor uses file_system_windows
    (2, 2, 1), -- executor uses file_system_unix
    (2, 3, 1); -- executor uses file_system

-- Insert sample group chats based on config.json
INSERT INTO group_chats (name, type, description, labels, selector_prompt, model_client, created_by) VALUES 
    ('file_system', 'round_robin_group_chat', '文件系统操作代理，负责处理文件和目录相关的操作', 
     '{"file_system", "agent"}', NULL, NULL, 1),
    ('prompt_flow', 'selector_group_chat', 'Prompt迭代器', 
     '{"prompt", "group_chat"}', 'group_chat/prompt_flow/selector_pt.md', 
     'deepseek-chat_DeepSeek', 1),
    ('hil', 'selector_group_chat', 'hil', 
     '{"group_chat", "hil"}', 'hil/hil_selector_pt.md', 
     'deepseek-chat_DeepSeek', 1);

-- Insert sample group chat participants
INSERT INTO group_chat_participants (group_chat_id, agent_id, participant_role, join_order, created_by) VALUES 
    (1, 1, 'participant', 1, 1), -- file_system group: prompt_refiner
    (2, 1, 'participant', 1, 1), -- prompt_flow group: prompt_refiner  
    (2, 2, 'participant', 2, 1), -- prompt_flow group: executor
    (3, 1, 'participant', 1, 1); -- hil group: prompt_refiner (assuming product_manager maps to agent id 1)

-- Insert sample prompts
INSERT INTO prompts (prompt_id, name, category, subcategories, description, agent_id, created_by) VALUES 
    ('prd_pt_v1', 'Product Requirements Document Template', 'agent', ARRAY['prd_pt'], 'Universal PRD framework generator', 1, 1),
    ('ui_designer_pt_v1', 'UI Designer Prompt Template', 'agent', ARRAY['ui_designer_pt'], 'UI design assistant prompt', 2, 1),
    ('prompt_refiner_system', 'Prompt Refiner System Message', 'agent', ARRAY['system_message'], 'System message for prompt refiner agent', 1, 1);

-- Insert sample threads
INSERT INTO threads (id, name, user_id, user_identifier, tags, thread_metadata) VALUES 
    ('550e8400-e29b-41d4-a716-446655440001', 'Welcome Chat Session', 2, 'admin', ARRAY['welcome', 'tutorial'], '{}'),
    ('550e8400-e29b-41d4-a716-446655440002', 'Agent Development Discussion', 3, 'developer', ARRAY['development', 'agent'], '{}'),
    ('550e8400-e29b-41d4-a716-446655440003', 'Prompt Review Session', 4, 'reviewer', ARRAY['review', 'prompts'], '{}');

-- Insert sample steps
INSERT INTO steps (id, name, type, thread_id, streaming, input, output, step_metadata) VALUES 
    ('650e8400-e29b-41d4-a716-446655440001', 'Welcome Message', 'system', '550e8400-e29b-41d4-a716-446655440001', FALSE, NULL, 'Welcome to AgentFusion! How can I help you today?', '{}'),
    ('650e8400-e29b-41d4-a716-446655440002', 'User Question', 'user', '550e8400-e29b-41d4-a716-446655440001', FALSE, 'How do I create a new agent?', NULL, '{}'),
    ('650e8400-e29b-41d4-a716-446655440003', 'Agent Response', 'assistant', '550e8400-e29b-41d4-a716-446655440001', FALSE, NULL, 'To create a new agent, you can use the agent builder interface...', '{}'),
    ('650e8400-e29b-41d4-a716-446655440004', 'Code Discussion', 'user', '550e8400-e29b-41d4-a716-446655440002', FALSE, 'Let me review the agent configuration', NULL, '{}');

-- Insert sample elements
INSERT INTO elements (id, thread_id, step_id, type, name, url, mime_type, size_bytes, props) VALUES 
    ('750e8400-e29b-41d4-a716-446655440001', '550e8400-e29b-41d4-a716-446655440001', '650e8400-e29b-41d4-a716-446655440003', 'file', 'agent_config.json', '/uploads/agent_config.json', 'application/json', 2048, '{}'),
    ('750e8400-e29b-41d4-a716-446655440002', '550e8400-e29b-41d4-a716-446655440002', '650e8400-e29b-41d4-a716-446655440004', 'image', 'architecture_diagram.png', '/uploads/architecture.png', 'image/png', 156789, '{}');

-- Insert sample feedbacks
INSERT INTO feedbacks (id, for_id, thread_id, user_id, value, comment, feedback_type) VALUES 
    ('850e8400-e29b-41d4-a716-446655440001', '650e8400-e29b-41d4-a716-446655440003', '550e8400-e29b-41d4-a716-446655440001', 2, 5, 'Very helpful response!', 'rating'),
    ('850e8400-e29b-41d4-a716-446655440002', '650e8400-e29b-41d4-a716-446655440003', '550e8400-e29b-41d4-a716-446655440001', 2, 1, NULL, 'thumbs');

-- ================================================
-- Useful Views
-- ================================================

-- View for user activity summary
CREATE VIEW user_activity_summary AS
SELECT 
    u.id as user_id,
    u.username,
    u.first_name || ' ' || u.last_name as full_name,
    COUNT(ual.id) as total_activities,
    COUNT(CASE WHEN ual.created_at >= CURRENT_TIMESTAMP - INTERVAL '24 hours' THEN 1 END) as activities_last_24h,
    COUNT(CASE WHEN ual.created_at >= CURRENT_TIMESTAMP - INTERVAL '7 days' THEN 1 END) as activities_last_week,
    MAX(ual.created_at) as last_activity,
    COUNT(CASE WHEN ual.status = 'failure' THEN 1 END) as failed_activities
FROM "User" u
LEFT JOIN user_activity_logs ual ON u.id = ual.user_id
WHERE u.is_active = TRUE
GROUP BY u.id, u.username, u.first_name, u.last_name;

-- View for active user sessions
CREATE VIEW active_user_sessions AS
SELECT 
    us.id as session_id,
    u.username,
    u.first_name || ' ' || u.last_name as full_name,
    us.ip_address,
    us.device_info->>'platform' as device_platform,
    us.device_info->>'browser' as device_browser,
    us.location_info->>'country' as country,
    us.location_info->>'city' as city,
    us.last_activity,
    us.created_at as session_started,
    us.expires_at
FROM user_sessions us
JOIN "User" u ON us.user_id = u.id
WHERE us.is_active = TRUE 
    AND us.expires_at > CURRENT_TIMESTAMP
ORDER BY us.last_activity DESC;

-- View for user API key status
CREATE VIEW user_api_key_status AS
SELECT 
    uak.id as api_key_id,
    u.username,
    uak.name as key_name,
    uak.key_prefix,
    uak.is_active,
    uak.rate_limit,
    uak.usage_count,
    uak.last_used,
    uak.expires_at,
    CASE 
        WHEN uak.expires_at IS NOT NULL AND uak.expires_at < CURRENT_TIMESTAMP THEN 'expired'
        WHEN NOT uak.is_active THEN 'disabled'
        ELSE 'active'
    END as status,
    uak.permissions
FROM user_api_keys uak
JOIN "User" u ON uak.user_id = u.id
ORDER BY u.username, uak.created_at DESC;

-- View for conversation threads with stats
CREATE VIEW thread_summary AS
SELECT 
    t.id as thread_id,
    t.name,
    u.username,
    u.first_name || ' ' || u.last_name as user_full_name,
    COUNT(s.id) as step_count,
    COUNT(e.id) as element_count,
    COUNT(f.id) as feedback_count,
    AVG(f.value) as avg_feedback,
    MAX(s.created_at) as last_activity,
    t.tags,
    t.thread_metadata,
    t.created_at,
    t.is_active
FROM threads t
JOIN "User" u ON t.user_id = u.id
LEFT JOIN steps s ON t.id = s.thread_id
LEFT JOIN elements e ON t.id = e.thread_id
LEFT JOIN feedbacks f ON t.id = f.thread_id
WHERE t.is_active = TRUE
GROUP BY t.id, t.name, u.username, u.first_name, u.last_name, t.tags, t.thread_metadata, t.created_at, t.is_active
ORDER BY last_activity DESC;

-- View for conversation flow
CREATE VIEW conversation_flow AS
SELECT 
    s.id as step_id,
    s.name as step_name,
    s.type,
    s.thread_id,
    t.name as thread_name,
    u.username,
    s.parent_id,
    s.input,
    s.output,
    s.is_error,
    s.start_time,
    s.end_time,
    s.created_at,
    CASE 
        WHEN s.end_time IS NOT NULL AND s.start_time IS NOT NULL 
        THEN EXTRACT(EPOCH FROM (s.end_time - s.start_time))
        ELSE NULL 
    END as duration_seconds
FROM steps s
JOIN threads t ON s.thread_id = t.id
JOIN "User" u ON t.user_id = u.id
ORDER BY s.thread_id, s.created_at;

-- View for element attachments
CREATE VIEW element_attachments AS
SELECT 
    e.id as element_id,
    e.name,
    e.type,
    e.mime_type,
    e.size_bytes,
    t.id as thread_id,
    t.name as thread_name,
    s.id as step_id,
    s.name as step_name,
    u.username as thread_owner,
    e.url,
    e.created_at
FROM elements e
LEFT JOIN threads t ON e.thread_id = t.id
LEFT JOIN steps s ON e.step_id = s.id
LEFT JOIN "User" u ON t.user_id = u.id
WHERE e.is_active = TRUE
ORDER BY e.created_at DESC;

-- View for feedback analytics
CREATE VIEW feedback_analytics AS
SELECT 
    t.id as thread_id,
    t.name as thread_name,
    u.username as thread_owner,
    f.feedback_type,
    COUNT(f.id) as feedback_count,
    AVG(f.value) as avg_rating,
    MIN(f.value) as min_rating,
    MAX(f.value) as max_rating,
    COUNT(CASE WHEN f.comment IS NOT NULL THEN 1 END) as comments_count
FROM threads t
JOIN "User" u ON t.user_id = u.id
LEFT JOIN feedbacks f ON t.id = f.thread_id
GROUP BY t.id, t.name, u.username, f.feedback_type
ORDER BY avg_rating DESC;

-- View for current prompt versions
CREATE VIEW current_prompt_versions AS
SELECT 
    p.prompt_id,
    p.name,
    p.category,
    p.subcategories,
    pv.version_number,
    pv.version_label,
    pv.content,
    pv.status,
    u1.username as created_by_username,
    u1.first_name || ' ' || u1.last_name as created_by_name,
    pv.created_at,
    u2.username as approved_by_username,
    u2.first_name || ' ' || u2.last_name as approved_by_name,
    pv.approved_at,
    a.name as agent_name,
    a.label as agent_label
FROM prompts p
JOIN prompt_versions pv ON p.id = pv.prompt_id
LEFT JOIN agents a ON p.agent_id = a.id
    LEFT JOIN "User" u1 ON pv.created_by = u1.id
    LEFT JOIN "User" u2 ON pv.approved_by = u2.id
WHERE pv.is_current = TRUE AND p.is_active = TRUE;

-- View for prompt change summary
CREATE VIEW prompt_change_summary AS
SELECT 
    p.prompt_id,
    p.name,
    COUNT(pv.id) as total_versions,
    MAX(pv.version_number) as latest_version,
    COUNT(pch.id) as total_changes,
    MAX(pch.changed_at) as last_changed
FROM prompts p
LEFT JOIN prompt_versions pv ON p.id = pv.prompt_id
LEFT JOIN prompt_change_history pch ON pv.id = pch.prompt_version_id
WHERE p.is_active = TRUE
GROUP BY p.id, p.prompt_id, p.name;

-- View for agent prompt mapping
CREATE VIEW agent_prompt_mapping AS
SELECT 
    a.name as agent_name,
    a.label as agent_label,
    ua.username as agent_created_by,
    p.prompt_id,
    p.name as prompt_name,
    p.category,
    p.subcategories,
    pv.version_number,
    pv.status,
    pv.is_current,
    upv.username as prompt_created_by,
    mc.label as model_client_label,
    mc.model_name,
    umc.username as model_client_created_by
FROM agents a
LEFT JOIN prompts p ON a.id = p.agent_id
LEFT JOIN prompt_versions pv ON p.id = pv.prompt_id
LEFT JOIN model_clients mc ON a.model_client_id = mc.id
LEFT JOIN "User" ua ON a.created_by = ua.id
LEFT JOIN "User" upv ON pv.created_by = upv.id
LEFT JOIN "User" umc ON mc.created_by = umc.id
WHERE a.is_active = TRUE AND (p.is_active = TRUE OR p.id IS NULL);

-- View for agent MCP servers mapping
CREATE VIEW agent_mcp_servers_view AS
SELECT 
    a.id as agent_id,
    a.agent_uuid,
    a.name as agent_name,
    a.label as agent_label,
    a.description as agent_description,
    ms.id as mcp_server_id,
    ms.server_uuid as mcp_server_uuid,
    ms.name as mcp_server_name,
    ms.command as mcp_command,
    ms.args as mcp_args,
    ms.env as mcp_env,
    ms.url as mcp_url,
    ms.headers as mcp_headers,
    ms.timeout as mcp_timeout,
    ms.sse_read_timeout as mcp_sse_read_timeout,
    ms.description as mcp_description,
    ams.is_active as relationship_active,
    ams.created_at as relationship_created_at,
    ua.username as agent_created_by,
    ums.username as mcp_server_created_by,
    urel.username as relationship_created_by
FROM agents a
LEFT JOIN agent_mcp_servers ams ON a.id = ams.agent_id
LEFT JOIN mcp_servers ms ON ams.mcp_server_id = ms.id
LEFT JOIN "User" ua ON a.created_by = ua.id
LEFT JOIN "User" ums ON ms.created_by = ums.id
LEFT JOIN "User" urel ON ams.created_by = urel.id
WHERE a.is_active = TRUE 
    AND (ms.is_active = TRUE OR ms.id IS NULL)
    AND (ams.is_active = TRUE OR ams.id IS NULL)
ORDER BY a.name, ms.name;

-- ================================================
-- User Management Functions
-- ================================================

-- Function to create a new user
CREATE OR REPLACE FUNCTION create_user(
    p_username VARCHAR,
    p_email VARCHAR,
    p_password_hash VARCHAR,
    p_first_name VARCHAR DEFAULT NULL,
    p_last_name VARCHAR DEFAULT NULL,
    p_role VARCHAR DEFAULT 'user',
    p_created_by_id INTEGER DEFAULT 1
) RETURNS INTEGER AS $$
DECLARE
    v_user_id INTEGER;
BEGIN
    INSERT INTO "User" (
        username, identifier, email, password_hash, first_name, last_name, 
        role, is_active, is_verified, created_by
    ) VALUES (
        p_username, p_username, p_email, p_password_hash, p_first_name, p_last_name,
        p_role, TRUE, FALSE, p_created_by_id
    ) RETURNING id INTO v_user_id;
    
    RETURN v_user_id;
END;
$$ LANGUAGE plpgsql;

-- Function to authenticate user and update last login
CREATE OR REPLACE FUNCTION authenticate_user(
    p_username VARCHAR,
    p_password_hash VARCHAR
) RETURNS TABLE (
    user_id INTEGER,
    username VARCHAR,
    email VARCHAR,
    role VARCHAR,
    is_active BOOLEAN,
    is_verified BOOLEAN
) AS $$
BEGIN
    -- Update last login on successful authentication
    UPDATE "User" 
    SET last_login = CURRENT_TIMESTAMP, 
        failed_login_attempts = 0 
    WHERE username = p_username 
        AND password_hash = p_password_hash 
        AND is_active = TRUE;
    
    -- Return user info if authentication successful
    RETURN QUERY
    SELECT u.id, u.username, u.email, u.role, u.is_active, u.is_verified
    FROM "User" u
    WHERE u.username = p_username 
        AND u.password_hash = p_password_hash 
        AND u.is_active = TRUE;
END;
$$ LANGUAGE plpgsql;

-- Function to handle failed login attempts
CREATE OR REPLACE FUNCTION record_failed_login(p_username VARCHAR) RETURNS VOID AS $$
BEGIN
    UPDATE "User" 
    SET failed_login_attempts = failed_login_attempts + 1,
        locked_until = CASE 
            WHEN failed_login_attempts >= 4 THEN CURRENT_TIMESTAMP + INTERVAL '30 minutes'
            ELSE locked_until
        END
    WHERE username = p_username AND is_active = TRUE;
END;
$$ LANGUAGE plpgsql;

-- Function to create password reset token
CREATE OR REPLACE FUNCTION create_password_reset_token(
    p_user_id INTEGER,
    p_token VARCHAR,
    p_token_hash VARCHAR,
    p_ip_address INET DEFAULT NULL,
    p_user_agent TEXT DEFAULT NULL
) RETURNS INTEGER AS $$
DECLARE
    v_token_id INTEGER;
BEGIN
    -- Invalidate existing tokens for user
    UPDATE password_reset_tokens 
    SET used_at = CURRENT_TIMESTAMP 
    WHERE user_id = p_user_id AND used_at IS NULL;
    
    -- Create new token
    INSERT INTO password_reset_tokens (
        user_id, token, token_hash, expires_at, ip_address, user_agent
    ) VALUES (
        p_user_id, p_token, p_token_hash, 
        CURRENT_TIMESTAMP + INTERVAL '1 hour',
        p_ip_address, p_user_agent
    ) RETURNING id INTO v_token_id;
    
    RETURN v_token_id;
END;
$$ LANGUAGE plpgsql;

-- Function to create user session
CREATE OR REPLACE FUNCTION create_user_session(
    p_user_id INTEGER,
    p_session_token VARCHAR,
    p_refresh_token VARCHAR DEFAULT NULL,
    p_ip_address INET DEFAULT NULL,
    p_user_agent TEXT DEFAULT NULL,
    p_device_info JSONB DEFAULT NULL,
    p_location_info JSONB DEFAULT NULL
) RETURNS INTEGER AS $$
DECLARE
    v_session_id INTEGER;
BEGIN
    INSERT INTO user_sessions (
        user_id, session_token, refresh_token, ip_address, 
        user_agent, device_info, location_info, expires_at
    ) VALUES (
        p_user_id, p_session_token, p_refresh_token, p_ip_address,
        p_user_agent, p_device_info, p_location_info,
        CURRENT_TIMESTAMP + INTERVAL '30 days'
    ) RETURNING id INTO v_session_id;
    
    RETURN v_session_id;
END;
$$ LANGUAGE plpgsql;

-- Function to log user activity
CREATE OR REPLACE FUNCTION log_user_activity(
    p_user_id INTEGER,
    p_activity_type VARCHAR,
    p_resource_type VARCHAR DEFAULT NULL,
    p_resource_id INTEGER DEFAULT NULL,
    p_action_details JSONB DEFAULT NULL,
    p_ip_address INET DEFAULT NULL,
    p_user_agent TEXT DEFAULT NULL,
    p_session_id INTEGER DEFAULT NULL,
    p_api_key_id INTEGER DEFAULT NULL,
    p_status VARCHAR DEFAULT 'success',
    p_error_message TEXT DEFAULT NULL
) RETURNS INTEGER AS $$
DECLARE
    v_log_id INTEGER;
BEGIN
    INSERT INTO user_activity_logs (
        user_id, activity_type, resource_type, resource_id, action_details,
        ip_address, user_agent, session_id, api_key_id, status, error_message
    ) VALUES (
        p_user_id, p_activity_type, p_resource_type, p_resource_id, p_action_details,
        p_ip_address, p_user_agent, p_session_id, p_api_key_id, p_status, p_error_message
    ) RETURNING id INTO v_log_id;
    
    RETURN v_log_id;
END;
$$ LANGUAGE plpgsql;

-- Function to set user preference
CREATE OR REPLACE FUNCTION set_user_preference(
    p_user_id INTEGER,
    p_preference_key VARCHAR,
    p_preference_value JSONB,
    p_category VARCHAR DEFAULT 'general',
    p_description TEXT DEFAULT NULL
) RETURNS VOID AS $$
BEGIN
    INSERT INTO user_preferences (user_id, preference_key, preference_value, category, description)
    VALUES (p_user_id, p_preference_key, p_preference_value, p_category, p_description)
    ON CONFLICT (user_id, preference_key) 
    DO UPDATE SET 
        preference_value = EXCLUDED.preference_value,
        category = EXCLUDED.category,
        description = EXCLUDED.description,
        updated_at = CURRENT_TIMESTAMP;
END;
$$ LANGUAGE plpgsql;

-- Function to get user preferences
CREATE OR REPLACE FUNCTION get_user_preferences(p_user_id INTEGER)
RETURNS TABLE (
    preference_key VARCHAR,
    preference_value JSONB,
    category VARCHAR,
    description TEXT
) AS $$
BEGIN
    RETURN QUERY
    SELECT up.preference_key, up.preference_value, up.category, up.description
    FROM user_preferences up
    WHERE up.user_id = p_user_id
    ORDER BY up.category, up.preference_key;
END;
$$ LANGUAGE plpgsql;

-- Function to create API key
CREATE OR REPLACE FUNCTION create_api_key(
    p_user_id INTEGER,
    p_name VARCHAR,
    p_key_prefix VARCHAR,
    p_key_hash VARCHAR,
    p_permissions JSONB DEFAULT '{}',
    p_rate_limit INTEGER DEFAULT 1000,
    p_expires_days INTEGER DEFAULT NULL
) RETURNS INTEGER AS $$
DECLARE
    v_api_key_id INTEGER;
    v_expires_at TIMESTAMP;
BEGIN
    -- Calculate expiration date
    IF p_expires_days IS NOT NULL THEN
        v_expires_at := CURRENT_TIMESTAMP + (p_expires_days || ' days')::INTERVAL;
    END IF;
    
    INSERT INTO user_api_keys (
        user_id, name, key_prefix, key_hash, permissions, 
        rate_limit, expires_at
    ) VALUES (
        p_user_id, p_name, p_key_prefix, p_key_hash, p_permissions,
        p_rate_limit, v_expires_at
    ) RETURNING id INTO v_api_key_id;
    
    RETURN v_api_key_id;
END;
$$ LANGUAGE plpgsql;

-- Function to create a new conversation thread
CREATE OR REPLACE FUNCTION create_thread(
    p_user_id INTEGER,
    p_name TEXT DEFAULT NULL,
    p_tags TEXT[] DEFAULT ARRAY[]::TEXT[],
    p_metadata JSONB DEFAULT '{}'
) RETURNS UUID AS $$
DECLARE
    v_thread_id UUID;
    v_user_identifier TEXT;
BEGIN
    -- Get user identifier for compatibility
    SELECT username INTO v_user_identifier FROM "User" WHERE id = p_user_id;
    
    INSERT INTO threads (
        name, user_id, user_identifier, tags, metadata
    ) VALUES (
        p_name, p_user_id, v_user_identifier, p_tags, p_metadata
    ) RETURNING id INTO v_thread_id;
    
    RETURN v_thread_id;
END;
$$ LANGUAGE plpgsql;

-- Function to add a step to a conversation
CREATE OR REPLACE FUNCTION add_step(
    p_thread_id UUID,
    p_name TEXT,
    p_type TEXT,
    p_parent_id UUID DEFAULT NULL,
    p_input TEXT DEFAULT NULL,
    p_output TEXT DEFAULT NULL,
    p_streaming BOOLEAN DEFAULT FALSE,
    p_metadata JSONB DEFAULT '{}'
) RETURNS UUID AS $$
DECLARE
    v_step_id UUID;
BEGIN
    INSERT INTO steps (
        name, type, thread_id, parent_id, input, output, 
        streaming, metadata
    ) VALUES (
        p_name, p_type, p_thread_id, p_parent_id, p_input, p_output,
        p_streaming, p_metadata
    ) RETURNING id INTO v_step_id;
    
    -- Update thread's updated_at timestamp
    UPDATE threads SET updated_at = CURRENT_TIMESTAMP WHERE id = p_thread_id;
    
    RETURN v_step_id;
END;
$$ LANGUAGE plpgsql;

-- Function to add an element/attachment
CREATE OR REPLACE FUNCTION add_element(
    p_thread_id UUID,
    p_type TEXT,
    p_name TEXT,
    p_step_id UUID DEFAULT NULL,
    p_url TEXT DEFAULT NULL,
    p_mime_type TEXT DEFAULT NULL,
    p_size_bytes BIGINT DEFAULT NULL,
    p_props JSONB DEFAULT '{}'
) RETURNS UUID AS $$
DECLARE
    v_element_id UUID;
BEGIN
    INSERT INTO elements (
        thread_id, step_id, type, name, url, mime_type, size_bytes, props
    ) VALUES (
        p_thread_id, p_step_id, p_type, p_name, p_url, p_mime_type, p_size_bytes, p_props
    ) RETURNING id INTO v_element_id;
    
    RETURN v_element_id;
END;
$$ LANGUAGE plpgsql;

-- Function to add feedback
CREATE OR REPLACE FUNCTION add_feedback(
    p_for_id UUID,
    p_thread_id UUID,
    p_user_id INTEGER,
    p_value INTEGER,
    p_comment TEXT DEFAULT NULL,
    p_feedback_type VARCHAR DEFAULT 'rating'
) RETURNS UUID AS $$
DECLARE
    v_feedback_id UUID;
BEGIN
    INSERT INTO feedbacks (
        for_id, thread_id, user_id, value, comment, feedback_type
    ) VALUES (
        p_for_id, p_thread_id, p_user_id, p_value, p_comment, p_feedback_type
    ) RETURNING id INTO v_feedback_id;
    
    RETURN v_feedback_id;
END;
$$ LANGUAGE plpgsql;

-- Function to get thread conversation history
CREATE OR REPLACE FUNCTION get_thread_conversation(p_thread_id UUID)
RETURNS TABLE (
    step_id UUID,
    step_name TEXT,
    step_type TEXT,
    parent_id UUID,
    input TEXT,
    output TEXT,
    created_at TIMESTAMP,
    elements JSONB
) AS $$
BEGIN
    RETURN QUERY
    SELECT 
        s.id,
        s.name,
        s.type,
        s.parent_id,
        s.input,
        s.output,
        s.created_at,
        COALESCE(
            json_agg(
                json_build_object(
                    'id', e.id,
                    'name', e.name,
                    'type', e.type,
                    'url', e.url,
                    'mime_type', e.mime_type
                ) ORDER BY e.created_at
            ) FILTER (WHERE e.id IS NOT NULL),
            '[]'::json
        )::jsonb as elements
    FROM steps s
    LEFT JOIN elements e ON s.id = e.step_id
    WHERE s.thread_id = p_thread_id
    GROUP BY s.id, s.name, s.type, s.parent_id, s.input, s.output, s.created_at
    ORDER BY s.created_at;
END;
$$ LANGUAGE plpgsql;

-- ================================================
-- Hybrid ID Helper Functions
-- ================================================

-- Function to get user by UUID (for external APIs)
CREATE OR REPLACE FUNCTION get_user_by_uuid(p_user_uuid UUID)
RETURNS TABLE (
    id INTEGER,
    user_uuid UUID,
    username VARCHAR,
    email VARCHAR,
    role VARCHAR,
    is_active BOOLEAN
) AS $$
BEGIN
    RETURN QUERY
    SELECT u.id, u.user_uuid, u.username, u.email, u.role, u.is_active
    FROM "User" u
    WHERE u.user_uuid = p_user_uuid AND u.is_active = TRUE;
END;
$$ LANGUAGE plpgsql;

-- Function to get agent by UUID (for external APIs)
CREATE OR REPLACE FUNCTION get_agent_by_uuid(p_agent_uuid UUID)
RETURNS TABLE (
    id INTEGER,
    agent_uuid UUID,
    name VARCHAR,
    label VARCHAR,
    description TEXT,
    is_active BOOLEAN
) AS $$
BEGIN
    RETURN QUERY
    SELECT a.id, a.agent_uuid, a.name, a.label, a.description, a.is_active
    FROM agents a
    WHERE a.agent_uuid = p_agent_uuid AND a.is_active = TRUE;
END;
$$ LANGUAGE plpgsql;

-- Function to get prompt by UUID (for external APIs)
CREATE OR REPLACE FUNCTION get_prompt_by_uuid(p_prompt_uuid UUID)
RETURNS TABLE (
    id INTEGER,
    prompt_uuid UUID,
    prompt_id VARCHAR,
    name VARCHAR,
    category VARCHAR,
    description TEXT,
    is_active BOOLEAN
) AS $$
BEGIN
    RETURN QUERY
    SELECT p.id, p.prompt_uuid, p.prompt_id, p.name, p.category, p.description, p.is_active
    FROM prompts p
    WHERE p.prompt_uuid = p_prompt_uuid AND p.is_active = TRUE;
END;
$$ LANGUAGE plpgsql;

-- Function to get internal ID from UUID (for performance-critical internal operations)
CREATE OR REPLACE FUNCTION get_user_id_from_uuid(p_user_uuid UUID) RETURNS INTEGER AS $$
DECLARE
    v_user_id INTEGER;
BEGIN
    SELECT id INTO v_user_id FROM "User" WHERE user_uuid = p_user_uuid;
    RETURN v_user_id;
END;
$$ LANGUAGE plpgsql;

-- ================================================
-- Useful Functions
-- ================================================

-- Function to get prompt history
CREATE OR REPLACE FUNCTION get_prompt_history(p_prompt_id VARCHAR)
RETURNS TABLE (
    version_number INTEGER,
    version_label VARCHAR,
    content TEXT,
    status VARCHAR,
    created_by_username VARCHAR,
    created_by_name TEXT,
    created_at TIMESTAMP,
    change_count BIGINT
) AS $$
BEGIN
    RETURN QUERY
    SELECT 
        pv.version_number,
        pv.version_label,
        pv.content,
        pv.status,
        u.username as created_by_username,
        u.first_name || ' ' || u.last_name as created_by_name,
        pv.created_at,
        COUNT(pch.id) as change_count
    FROM prompts p
    JOIN prompt_versions pv ON p.id = pv.prompt_id
    LEFT JOIN "User" u ON pv.created_by = u.id
    LEFT JOIN prompt_change_history pch ON pv.id = pch.prompt_version_id
    WHERE p.prompt_id = p_prompt_id
    GROUP BY pv.id, pv.version_number, pv.version_label, pv.content, pv.status, u.username, u.first_name, u.last_name, pv.created_at
    ORDER BY pv.version_number DESC;
END;
$$ LANGUAGE plpgsql;

-- Function to create new prompt version
CREATE OR REPLACE FUNCTION create_prompt_version(
    p_prompt_id VARCHAR,
    p_content TEXT,
    p_version_label VARCHAR DEFAULT NULL,
    p_created_by_id INTEGER DEFAULT 1, -- Default to system user
    p_change_reason TEXT DEFAULT NULL
) RETURNS INTEGER AS $$
DECLARE
    v_prompt_table_id INTEGER;
    v_next_version INTEGER;
    v_new_version_id INTEGER;
BEGIN
    -- Get prompt table ID
    SELECT id INTO v_prompt_table_id FROM prompts WHERE prompt_id = p_prompt_id;
    
    IF v_prompt_table_id IS NULL THEN
        RAISE EXCEPTION 'Prompt with ID % not found', p_prompt_id;
    END IF;
    
    -- Get next version number
    SELECT COALESCE(MAX(version_number), 0) + 1 
    INTO v_next_version 
    FROM prompt_versions 
    WHERE prompt_id = v_prompt_table_id;
    
    -- Insert new version
    INSERT INTO prompt_versions (
        prompt_id, version_number, version_label, content, 
        content_hash, created_by, is_current
    ) VALUES (
        v_prompt_table_id, v_next_version, p_version_label, p_content,
        encode(sha256(p_content::bytea), 'hex'), p_created_by_id, TRUE
    ) RETURNING id INTO v_new_version_id;
    
    -- Add change reason if provided
    IF p_change_reason IS NOT NULL THEN
        INSERT INTO prompt_change_history (
            prompt_version_id, change_type, change_description, 
            new_content, changed_by, change_reason
        ) VALUES (
            v_new_version_id, 'created', 'New version created with reason',
            p_content, p_created_by_id, p_change_reason
        );
    END IF;
    
    RETURN v_new_version_id;
END;
$$ LANGUAGE plpgsql;

-- ================================================
-- Hybrid ID Strategy (Serial + UUID)
-- ================================================

/*
HYBRID ID DESIGN PATTERN:

1. INTERNAL USE (Performance):
   - All tables use SERIAL (auto-increment integer) as PRIMARY KEY
   - All foreign key relationships use SERIAL IDs for best performance
   - Internal queries and joins use SERIAL IDs

2. EXTERNAL USE (Security):
   - Selected tables have additional UUID columns for external APIs
   - UUIDs are used in REST endpoints, public URLs, and client-facing interfaces
   - UUIDs prevent enumeration attacks and information leakage

USAGE EXAMPLES:

-- Internal query (fast performance):
SELECT * FROM "User" u 
JOIN threads t ON u.id = t.user_id 
WHERE u.id = 12345;

-- External API query (secure):
SELECT * FROM "User" u 
JOIN threads t ON u.id = t.user_id 
WHERE u.user_uuid = '550e8400-e29b-41d4-a716-446655440000';

-- External API endpoints should use UUIDs:
GET /api/users/550e8400-e29b-41d4-a716-446655440000
GET /api/agents/7b2c8d1a-3f5e-4a9b-8c7d-1e2f3a4b5c6d
GET /api/prompts/9a8b7c6d-5e4f-3a2b-1c9d-8e7f6a5b4c3d

-- Tables with hybrid strategy:
- User: id (SERIAL) + user_uuid (UUID)
- model_clients: id (SERIAL) + client_uuid (UUID)  
- agents: id (SERIAL) + agent_uuid (UUID)
- prompts: id (SERIAL) + prompt_uuid (UUID)
- prompt_versions: id (SERIAL) + version_uuid (UUID)

-- Tables using UUID as primary key (already secure):
- threads: id (UUID PRIMARY KEY)
- steps: id (UUID PRIMARY KEY)
- elements: id (UUID PRIMARY KEY)  
- feedbacks: id (UUID PRIMARY KEY)
*/

-- ================================================
-- Comments and Documentation
-- ================================================

COMMENT ON TABLE "User" IS 'User accounts with authentication and role management';
COMMENT ON COLUMN "User".identifier IS 'Unique identifier for Chainlit compatibility (usually same as username)';
COMMENT ON TABLE password_reset_tokens IS 'Secure tokens for password reset functionality';
COMMENT ON TABLE user_sessions IS 'User login sessions with device and location tracking';
COMMENT ON TABLE user_preferences IS 'User-specific application preferences and settings';
COMMENT ON TABLE user_api_keys IS 'API keys for programmatic access with rate limiting';
COMMENT ON TABLE user_activity_logs IS 'Comprehensive audit log of user actions';
COMMENT ON TABLE threads IS 'Conversation threads/chat sessions between users and agents';
COMMENT ON TABLE steps IS 'Individual steps/messages within a conversation thread';
COMMENT ON TABLE elements IS 'File attachments, images, and other media elements in conversations';
COMMENT ON TABLE feedbacks IS 'User feedback and ratings on conversation steps and responses';
COMMENT ON TABLE agents IS 'Stores AI agent definitions and configurations';
COMMENT ON TABLE prompts IS 'Main prompt definitions with business identifiers';
COMMENT ON TABLE prompt_versions IS 'Version history for prompts with content and metadata';
COMMENT ON TABLE prompt_change_history IS 'Detailed change tracking for prompt modifications';
COMMENT ON TABLE model_clients IS 'Model client configurations for agents';
COMMENT ON TABLE component_types IS 'Lookup table for component types';
COMMENT ON TABLE agent_mcp_servers IS 'Many-to-many relationship between agents and MCP servers';

COMMENT ON COLUMN "User".avatar_url IS 'URL to user avatar image';
COMMENT ON COLUMN "User".timezone IS 'User timezone for proper datetime display';
COMMENT ON COLUMN "User".language IS 'Preferred interface language code (ISO 639-1)';
COMMENT ON COLUMN "User".email_verified_at IS 'Timestamp when email was verified';
COMMENT ON COLUMN password_reset_tokens.token_hash IS 'Hashed token for security (never store plain text)';
COMMENT ON COLUMN user_sessions.device_info IS 'JSON containing device platform, browser, OS details';
COMMENT ON COLUMN user_sessions.location_info IS 'JSON containing country, city, timezone from IP';
COMMENT ON COLUMN user_preferences.preference_value IS 'JSON value allowing complex preference data';
COMMENT ON COLUMN user_api_keys.key_hash IS 'Hashed API key for secure storage';
COMMENT ON COLUMN user_api_keys.permissions IS 'JSON defining specific API permissions';
COMMENT ON COLUMN user_api_keys.ip_whitelist IS 'Array of allowed IP addresses for key usage';
COMMENT ON COLUMN user_activity_logs.action_details IS 'JSON containing detailed action context';
COMMENT ON COLUMN threads.user_identifier IS 'Legacy compatibility field for Chainlit integration';
COMMENT ON COLUMN threads.tags IS 'Array of tags for categorizing conversations';
COMMENT ON COLUMN threads.thread_metadata IS 'JSON metadata for conversation context and settings';
COMMENT ON COLUMN steps.parent_id IS 'Reference to parent step for threaded conversations';
COMMENT ON COLUMN steps.streaming IS 'Whether this step involved streaming response';
COMMENT ON COLUMN steps.generation IS 'JSON metadata about AI generation (tokens, model, etc.)';
COMMENT ON COLUMN steps.show_input IS 'Formatted input text for display purposes';
COMMENT ON COLUMN elements.step_id IS 'Optional link to specific conversation step';
COMMENT ON COLUMN elements.chainlit_key IS 'Chainlit-specific key for element identification';
COMMENT ON COLUMN elements.for_id IS 'Reference to related element or step';
COMMENT ON COLUMN elements.props IS 'JSON properties for element rendering and behavior';
COMMENT ON COLUMN feedbacks.for_id IS 'UUID of step, element, or other entity being rated';
COMMENT ON COLUMN feedbacks.feedback_type IS 'Type of feedback: rating, thumbs, stars, etc.';
COMMENT ON COLUMN prompt_versions.content_hash IS 'SHA256 hash of content for integrity verification';
COMMENT ON COLUMN prompt_versions.is_current IS 'Indicates if this is the current active version';
COMMENT ON COLUMN prompt_change_history.diff_info IS 'Detailed diff information in JSON format';
COMMENT ON COLUMN model_clients.model_info IS 'JSON model capabilities and metadata';


