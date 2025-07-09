# AgentFusion Authentication System

基于数据库的安全认证系统，包含用户管理、密码哈希、失败登录保护和活动日志功能。

## 功能特性

### 🔐 安全认证
- **密码哈希**: 使用 bcrypt 进行安全的密码哈希
- **账户锁定**: 5次失败登录后自动锁定30分钟
- **活动日志**: 记录所有登录尝试和用户活动
- **角色管理**: 支持 user、admin、reviewer、developer 角色

### 🎯 核心功能
- 数据库用户验证
- 失败登录次数跟踪
- 账户激活/停用
- 密码重置
- 用户会话管理
- API密钥管理

## 数据库结构

系统使用以下主要表：
- `users` - 用户基本信息
- `user_sessions` - 用户会话
- `user_activity_logs` - 活动日志
- `password_reset_tokens` - 密码重置令牌
- `user_api_keys` - API密钥管理

## 安装依赖

更新 `pyproject.toml` 中的依赖：

```toml
dependencies = [
    "chainlit>=2.6.0",
    "bcrypt>=4.0.0",
    "asyncpg>=0.29.0",
    "sqlalchemy>=2.0.0"
]
```

安装依赖：

```bash
pip install bcrypt asyncpg sqlalchemy
```

## 配置

### 1. 数据库连接

在 `auth.py` 中配置数据库连接：

```python
# Docker Compose 环境
DATABASE_URL = "postgresql://postgres:postgres@db:5432/agentfusion"

# 本地开发环境
DATABASE_URL = "postgresql://postgres:postgres@localhost:5432/agentfusion"
```

### 2. 环境变量 (可选)

```bash
export DATABASE_URL="postgresql://postgres:postgres@db:5432/agentfusion"
export BCRYPT_ROUNDS=12  # 默认使用 bcrypt 默认值
```

## 使用方法

### 1. 初始化数据库

确保数据库已创建并运行了 `sql/progresdb.sql` 脚本来创建表结构。

### 2. 快速设置 (推荐)

```bash
cd python/packages/agent_fusion/src/chainlit_web/user/
python setup_auth.py
```

这将：
- 测试数据库连接
- 创建默认管理员用户 (admin/admin123!)
- 创建演示用户 (demo/demo123!)
- 验证认证系统

### 3. 手动创建用户

```bash
python user_manager.py create-defaults
```

或使用交互式创建：
```bash
python user_manager.py create-user
```

### 4. 用户管理命令

#### 交互式创建用户
```bash
python user_manager.py create-user
```

#### 列出所有用户
```bash
python user_manager.py list-users
```

#### 重置密码
```bash
python user_manager.py reset-password username
```

#### 激活/停用用户
```bash
python user_manager.py activate-user username
python user_manager.py deactivate-user username
```

#### 解锁被锁定的账户
```bash
python user_manager.py unlock-user username
```

## 在 Chainlit 中使用

认证系统会自动集成到 Chainlit 中：

```python
from chainlit_web.user.auth import auth_callback, get_data_layer

# Chainlit 会自动使用这些函数进行认证
```

登录时用户需要提供：
- **用户名** 或 **邮箱**
- **密码**

## API 使用示例

### 程序化创建用户

```python
from chainlit_web.user.auth import db_auth

# 创建用户
user_id = await db_auth.create_user(
    username="newuser",
    email="user@example.com",
    password="securepassword",
    role="user",
    first_name="New",
    last_name="User"
)
```

### 验证用户

```python
# 验证登录
user_data = await db_auth.authenticate_user(
    username="newuser",
    password="securepassword",
    ip_address="192.168.1.100"
)

if user_data:
    print(f"Login successful: {user_data['username']}")
else:
    print("Login failed")
```

## 安全特性

### 1. 密码安全
- 使用 bcrypt 哈希算法
- 自动生成盐值
- 密码不会以明文存储

### 2. 账户保护
- 5次失败登录后锁定30分钟
- 可追踪失败登录次数
- 管理员可手动解锁账户

### 3. 活动日志
所有用户活动都会记录：
- 登录成功/失败
- 密码重置
- 账户状态变更
- 用户创建/删除

### 4. 会话管理
- 支持多设备登录
- 会话过期管理
- IP地址跟踪

## Docker 部署

在 Docker Compose 环境中，确保：

1. 数据库服务正在运行：
```yaml
services:
  db:
    image: postgres:15
    environment:
      POSTGRES_DB: agentfusion
      POSTGRES_USER: postgres
      POSTGRES_PASSWORD: postgres
```

2. 应用连接到正确的数据库主机：
```python
DATABASE_URL = "postgresql://postgres:postgres@db:5432/agentfusion"
```

## 故障排除

### 1. 数据库连接失败
```bash
# 检查数据库是否运行
docker-compose ps db

# 查看数据库日志
docker-compose logs db
```

### 2. 密码哈希错误
确保安装了正确版本的 bcrypt：
```bash
pip install bcrypt>=4.0.0
```

### 3. 用户锁定问题
使用管理工具解锁：
```bash
python user_manager.py unlock-user username
```

### 4. 查看活动日志
```sql
SELECT * FROM user_activity_logs 
WHERE user_id = 1 
ORDER BY created_at DESC 
LIMIT 10;
```

## 最佳实践

1. **生产环境**：
   - 修改默认密码
   - 使用强密码策略
   - 定期审查用户活动日志

2. **安全配置**：
   - 启用 HTTPS
   - 配置防火墙
   - 定期备份数据库

3. **监控**：
   - 监控失败登录尝试
   - 定期清理过期会话
   - 审查用户权限

## 相关文件

- `auth.py` - 核心认证逻辑
- `user_manager.py` - 用户管理CLI工具
- `../../../sql/progresdb.sql` - 数据库表结构
- `../../../.devcontainer/docker-compose.yml` - Docker配置

## 技术栈

- **Python 3.11+**
- **PostgreSQL 15**
- **Chainlit** - Web界面框架
- **bcrypt** - 密码哈希
- **asyncpg** - PostgreSQL异步驱动
- **SQLAlchemy** - ORM框架 