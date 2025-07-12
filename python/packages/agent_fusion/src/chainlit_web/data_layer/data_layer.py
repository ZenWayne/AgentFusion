import hashlib
import bcrypt
import secrets
import json
import uuid
import aiofiles
from typing import Optional, Dict, Any, List, Union, TYPE_CHECKING
from datetime import datetime
import asyncio
import asyncpg
import chainlit as cl
from chainlit.data.base import BaseDataLayer
from chainlit.data.storage_clients.base import BaseStorageClient
from chainlit.data.utils import queue_until_user_message
from chainlit.element import ElementDict
from chainlit.logger import logger
from chainlit.step import StepDict
from chainlit.types import (
    Feedback,
    FeedbackDict,
    PageInfo,
    PaginatedResponse,
    Pagination,
    ThreadDict,
    ThreadFilter,
)
from chainlit.user import User
from dataclasses import dataclass

if TYPE_CHECKING:
    from chainlit.element import Element, ElementDict
    from chainlit.step import StepDict

ISO_FORMAT = "%Y-%m-%dT%H:%M:%S.%fZ"

@dataclass
class PersistedUserFields:
    id: int
    uuid: str
    createdAt: str

@dataclass
class PersistedUser(User, PersistedUserFields):
    pass

class AgentFusionUser(PersistedUser):
    """Extended PersistedUser class with additional AgentFusion-specific fields"""
    
    def __init__(self, 
                 id: int,
                 uuid: Optional[str] = None,
                 identifier: str = None,
                 display_name: Optional[str] = None,
                 email: Optional[str] = None,
                 password: Optional[str] = None,
                 role: str = "user",
                 first_name: Optional[str] = None,
                 last_name: Optional[str] = None,
                 createdAt: Optional[str] = None,
                 **kwargs):
        """
        Initialize AgentFusionUser
        
        Args:
            id: User ID (UUID)
            uuid: User UUID (optional, defaults to id)
            identifier: Unique identifier (username)
            display_name: Display name for the user
            email: User email
            password: Plain text password (will be hashed)
            role: User role (user, admin, reviewer, developer)
            first_name: First name
            last_name: Last name
            createdAt: Creation timestamp
            **kwargs: Additional metadata
        """
        # Prepare metadata with all our custom fields
        metadata = {
            "email": email,
            "password": password,  # Will be hashed by data layer
            "role": role,
            "first_name": first_name,
            "last_name": last_name,
            **kwargs
        }
        
        # Remove None values
        metadata = {k: v for k, v in metadata.items() if v is not None}
        
        super().__init__(
            id=id,
            uuid=uuid,
            identifier=identifier or id,
            createdAt=createdAt or datetime.now().isoformat(),
            metadata=metadata
        )
        
        # Override display_name if provided
        if display_name:
            self.display_name = display_name
    
    @property
    def email(self) -> Optional[str]:
        return self.metadata.get("email")
    
    @property
    def role(self) -> str:
        return self.metadata.get("role", "user")
    
    @property
    def first_name(self) -> Optional[str]:
        return self.metadata.get("first_name")
    
    @property
    def last_name(self) -> Optional[str]:
        return self.metadata.get("last_name")
    
    @property
    def password(self) -> Optional[str]:
        return self.metadata.get("password")


class AgentFusionDataLayer(BaseDataLayer):
    """Enhanced data layer with authentication and security features"""
    
    def __init__(
        self,
        database_url: str,
        storage_client: Optional[BaseStorageClient] = None,
        show_logger: bool = False,
        **kwargs
    ):
        self.database_url = database_url
        self.pool: Optional[asyncpg.Pool] = None
        self.storage_client = storage_client
        self.show_logger = show_logger

    async def connect(self):
        if not self.pool:
            self.pool = await asyncpg.create_pool(self.database_url)

    async def get_current_timestamp(self) -> datetime:
        return datetime.now()

    async def execute_query(
        self, query: str, params: Union[Dict, None] = None
    ) -> List[Dict[str, Any]]:
        if not self.pool:
            await self.connect()

        async with self.pool.acquire() as connection:  # type: ignore
            try:
                if params:
                    records = await connection.fetch(query, *params.values())
                else:
                    records = await connection.fetch(query)
                return [dict(record) for record in records]
            except Exception as e:
                logger.error(f"Database error: {e!s}")
                raise

    async def get_user(self, identifier: str) -> Optional[PersistedUser]:
        query = """
        SELECT * FROM "User" 
        WHERE identifier = $1
        """
        result = await self.execute_query(query, {"identifier": identifier})
        if not result or len(result) == 0:
            return None
        row = result[0]

        return PersistedUser(
            id=str(row.get("id")),
            uuid=str(row.get("user_uuid")),
            identifier=str(row.get("identifier")),
            createdAt=row.get("created_at").isoformat(),  # type: ignore
            metadata=json.loads(row.get("metadata", "{}")),
        )

    async def delete_feedback(self, feedback_id: str) -> bool:
        query = """
        DELETE FROM feedbacks WHERE id = $1
        """
        await self.execute_query(query, {"feedback_id": feedback_id})
        return True

    async def upsert_feedback(self, feedback: Feedback) -> str:
        query = """
        INSERT INTO feedbacks (id, for_id, thread_id, user_id, value, comment, feedback_type)
        VALUES ($1, $2, $3, $4, $5, $6, $7)
        ON CONFLICT (id) DO UPDATE
        SET value = EXCLUDED.value, comment = EXCLUDED.comment
        RETURNING id
        """
        feedback_id = feedback.id or str(uuid.uuid4())
        
        # Get thread_id from step if not provided
        thread_id = None
        if feedback.forId:
            step_query = """SELECT thread_id FROM steps WHERE id = $1"""
            step_result = await self.execute_query(step_query, {"step_id": feedback.forId})
            thread_id = step_result[0]["thread_id"] if step_result else None
        
        params = {
            "id": feedback_id,
            "for_id": feedback.forId,
            "thread_id": thread_id,
            "user_id": None,  # Will be set by authentication context if available
            "value": float(feedback.value),
            "comment": feedback.comment,
            "feedback_type": "rating",  # Default feedback type
        }
        results = await self.execute_query(query, params)
        return str(results[0]["id"])

    @queue_until_user_message()
    async def create_element(self, element: "Element"):
        if not self.storage_client:
            logger.warning(
                "Data Layer: create_element error. No cloud storage configured!"
            )
            return

        if not element.for_id:
            return

        if element.thread_id:
            query = 'SELECT id FROM threads WHERE id = $1'
            results = await self.execute_query(query, {"thread_id": element.thread_id})
            if not results:
                await self.update_thread(thread_id=element.thread_id)

        if element.for_id:
            query = 'SELECT id FROM steps WHERE id = $1'
            results = await self.execute_query(query, {"step_id": element.for_id})
            if not results:
                await self.create_step(
                    {
                        "id": element.for_id,
                        "metadata": {},
                        "type": "run",
                        "start_time": await self.get_current_timestamp(),
                        "end_time": await self.get_current_timestamp(),
                    }
                )
        content: Optional[Union[bytes, str]] = None

        if element.path:
            async with aiofiles.open(element.path, "rb") as f:
                content = await f.read()
        elif element.content:
            content = element.content
        elif not element.url:
            raise ValueError("Element url, path or content must be provided")

        if element.thread_id:
            path = f"threads/{element.thread_id}/files/{element.id}"
        else:
            path = f"files/{element.id}"

        if content is not None:
            await self.storage_client.upload_file(
                object_key=path,
                data=content,
                mime=element.mime or "application/octet-stream",
                overwrite=True,
            )

        query = """
        INSERT INTO elements (
            id, thread_id, step_id, metadata, mime_type, name, object_key, url,
            chainlit_key, display, size_bytes, language, page_number, props
        ) VALUES (
            $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14
        )
        ON CONFLICT (id) DO UPDATE SET
            props = EXCLUDED.props
        """
        params = {
            "id": element.id,
            "thread_id": element.thread_id,
            "step_id": element.for_id,
            "metadata": json.dumps(
                {
                    "size": element.size,
                    "language": element.language,
                    "display": element.display,
                    "type": element.type,
                    "page": getattr(element, "page", None),
                }
            ),
            "mime_type": element.mime,
            "name": element.name,
            "object_key": path,
            "url": element.url,
            "chainlit_key": element.chainlit_key,
            "display": element.display,
            "size_bytes": element.size,
            "language": element.language,
            "page_number": getattr(element, "page", None),
            "props": json.dumps(getattr(element, "props", {})),
        }
        await self.execute_query(query, params)

    async def get_element(
        self, thread_id: str, element_id: str
    ) -> Optional[ElementDict]:
        query = """
        SELECT * FROM elements
        WHERE id = $1 AND thread_id = $2
        """
        results = await self.execute_query(
            query, {"element_id": element_id, "thread_id": thread_id}
        )

        if not results:
            return None

        row = results[0]
        metadata = json.loads(row.get("metadata", "{}"))

        return ElementDict(
            id=str(row["id"]),
            threadId=str(row["thread_id"]),
            type=metadata.get("type", "file"),
            url=str(row["url"]),
            name=str(row["name"]),
            mime=str(row["mime_type"]),
            objectKey=str(row["object_key"]),
            forId=str(row["step_id"]),
            chainlitKey=row.get("chainlit_key"),
            display=row["display"],
            size=row["size_bytes"],
            language=row["language"],
            page=row["page_number"],
            autoPlay=row.get("autoPlay"),
            playerConfig=row.get("playerConfig"),
            props=json.loads(row.get("props", "{}")),
        )

    @queue_until_user_message()
    async def delete_element(self, element_id: str, thread_id: Optional[str] = None):
        query = """
        SELECT * FROM elements
        WHERE id = $1
        """
        elements = await self.execute_query(query, {"id": element_id})

        if self.storage_client is not None and len(elements) > 0:
            if elements[0]["object_key"]:
                await self.storage_client.delete_file(
                    object_key=elements[0]["object_key"]
                )
        query = """
        DELETE FROM elements 
        WHERE id = $1
        """
        params = {"id": element_id}

        if thread_id:
            query += ' AND thread_id = $2'
            params["thread_id"] = thread_id

        await self.execute_query(query, params)

    @queue_until_user_message()
    async def create_step(self, step_dict: StepDict):
        if step_dict.get("threadId"):
            thread_query = 'SELECT id FROM threads WHERE id = $1'
            thread_results = await self.execute_query(
                thread_query, {"thread_id": step_dict["threadId"]}
            )
            if not thread_results:
                await self.update_thread(thread_id=step_dict["threadId"])

        if step_dict.get("parentId"):
            parent_query = 'SELECT id FROM steps WHERE id = $1'
            parent_results = await self.execute_query(
                parent_query, {"parent_id": step_dict["parentId"]}
            )
            if not parent_results:
                await self.create_step(
                    {
                        "id": step_dict["parentId"],
                        "metadata": {},
                        "type": "run",
                        "createdAt": step_dict.get("createdAt"),
                    }
                )

        query = """
        INSERT INTO steps (
            id, thread_id, parent_id, input, metadata, name, output,
            type, start_time, end_time, show_input, is_error
        ) VALUES (
            $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12
        )
        ON CONFLICT (id) DO UPDATE SET
            parent_id = COALESCE(EXCLUDED.parent_id, steps.parent_id),
            input = COALESCE(EXCLUDED.input, steps.input),
            metadata = CASE 
                WHEN EXCLUDED.metadata <> '{}' THEN EXCLUDED.metadata 
                ELSE steps.metadata 
            END,
            name = COALESCE(EXCLUDED.name, steps.name),
            output = COALESCE(EXCLUDED.output, steps.output),
            type = CASE 
                WHEN EXCLUDED.type = 'run' THEN steps.type 
                ELSE EXCLUDED.type 
            END,
            thread_id = COALESCE(EXCLUDED.thread_id, steps.thread_id),
            end_time = COALESCE(EXCLUDED.end_time, steps.end_time),
            start_time = LEAST(EXCLUDED.start_time, steps.start_time),
            show_input = COALESCE(EXCLUDED.show_input, steps.show_input),
            is_error = COALESCE(EXCLUDED.is_error, steps.is_error)
        """

        timestamp = await self.get_current_timestamp()
        created_at = step_dict.get("createdAt")
        if created_at:
            timestamp = datetime.strptime(created_at, ISO_FORMAT)

        params = {
            "id": step_dict["id"],
            "thread_id": step_dict.get("threadId"),
            "parent_id": step_dict.get("parentId"),
            "input": step_dict.get("input"),
            "metadata": json.dumps(step_dict.get("metadata", {})),
            "name": step_dict.get("name"),
            "output": step_dict.get("output"),
            "type": step_dict["type"],
            "start_time": timestamp,
            "end_time": timestamp,
            "show_input": str(step_dict.get("showInput", "json")),
            "is_error": step_dict.get("isError", False),
        }
        await self.execute_query(query, params)

    @queue_until_user_message()
    async def update_step(self, step_dict: StepDict):
        await self.create_step(step_dict)

    @queue_until_user_message()
    async def delete_step(self, step_id: str):
        # Delete associated elements and feedbacks first
        await self.execute_query(
            'DELETE FROM elements WHERE step_id = $1', {"step_id": step_id}
        )
        await self.execute_query(
            'DELETE FROM feedbacks WHERE for_id = $1', {"step_id": step_id}
        )
        # Delete the step
        await self.execute_query(
            'DELETE FROM steps WHERE id = $1', {"step_id": step_id}
        )

    async def get_thread_author(self, thread_id: str) -> str:
        query = """
        SELECT u.identifier 
        FROM threads t
        JOIN "User" u ON t."user_id" = u.id
        WHERE t.id = $1
        """
        results = await self.execute_query(query, {"thread_id": thread_id})
        if not results:
            raise ValueError(f"Thread {thread_id} not found")
        return results[0]["identifier"]

    async def delete_thread(self, thread_id: str):
        elements_query = """
        SELECT * FROM elements 
        WHERE thread_id = $1
        """
        elements_results = await self.execute_query(
            elements_query, {"thread_id": thread_id}
        )

        if self.storage_client is not None:
            for elem in elements_results:
                if elem["objectKey"]:
                    await self.storage_client.delete_file(object_key=elem["objectKey"])

        await self.execute_query(
            'DELETE FROM threads WHERE id = $1', {"thread_id": thread_id}
        )

    async def list_threads(
        self, pagination: Pagination, filters: ThreadFilter
    ) -> PaginatedResponse[ThreadDict]:
        query = """
        SELECT 
            t.*, 
            u.identifier as user_identifier,
            u.user_uuid as user_uuid,
            (SELECT COUNT(*) FROM threads WHERE "user_id" = t."user_id") as total
        FROM threads t
        LEFT JOIN "User" u ON t."user_id" = u.id
        WHERE t."deleted_at" IS NULL
        """
        params: Dict[str, Any] = {}
        param_count = 1

        if filters.search:
            query += f" AND t.name ILIKE ${param_count}"
            params["name"] = f"%{filters.search}%"
            param_count += 1

        if filters.userId:
            query += f' AND t."user_id" = ${param_count}'
            params["user_id"] = int(filters.userId)
            param_count += 1

        if pagination.cursor:
            query += f' AND t."created_at" < (SELECT "created_at" FROM threads WHERE id = ${param_count})'
            params["cursor"] = pagination.cursor
            param_count += 1

        query += f' ORDER BY t."created_at" DESC LIMIT ${param_count}'
        params["limit"] = pagination.first + 1

        results = await self.execute_query(query, params)
        threads = results

        has_next_page = len(threads) > pagination.first
        if has_next_page:
            threads = threads[:-1]

        thread_dicts = []
        for thread in threads:
            thread_dict = ThreadDict(
                id=str(thread["id"]),
                createdAt=thread["created_at"].isoformat(),
                name=thread["name"],
                userId=str(thread["user_uuid"]) if thread["user_uuid"] else None,
                userIdentifier=thread["user_identifier"],
                metadata=json.loads(thread["metadata"]),
                steps=[],
                elements=[],
                tags=[],
            )
            thread_dicts.append(thread_dict)

        return PaginatedResponse(
            pageInfo=PageInfo(
                hasNextPage=has_next_page,
                startCursor=thread_dicts[0]["id"] if thread_dicts else None,
                endCursor=thread_dicts[-1]["id"] if thread_dicts else None,
            ),
            data=thread_dicts,
        )

    async def get_thread(self, thread_id: str) -> Optional[ThreadDict]:
        query = """
        SELECT t.*, u.identifier as user_identifier, u.user_uuid as user_uuid
        FROM threads t
        LEFT JOIN "User" u ON t."user_id" = u.id
        WHERE t.id = $1 AND t."deleted_at" IS NULL
        """
        results = await self.execute_query(query, {"thread_id": thread_id})

        if not results:
            return None

        thread = results[0]

        # Get steps and related feedback
        steps_query = """
        SELECT  s.*, 
                f.id feedback_id, 
                f.value feedback_value, 
                f.comment feedback_comment
        FROM steps s left join feedbacks f on s.id = f.for_id
        WHERE s.thread_id = $1
        ORDER BY start_time
        """
        steps_results = await self.execute_query(steps_query, {"thread_id": thread_id})

        # Get elements
        elements_query = """
        SELECT * FROM elements 
        WHERE thread_id = $1
        """
        elements_results = await self.execute_query(
            elements_query, {"thread_id": thread_id}
        )

        if self.storage_client is not None:
            for elem in elements_results:
                if not elem["url"] and elem["objectKey"]:
                    elem["url"] = await self.storage_client.get_read_url(
                        object_key=elem["objectKey"],
                    )

        return ThreadDict(
            id=str(thread["id"]),
            createdAt=thread["created_at"].isoformat(),
            name=thread["name"],
            userId=str(thread["user_uuid"]) if thread["user_uuid"] else None,
            userIdentifier=thread["user_identifier"],
            metadata=json.loads(thread["metadata"]),
            steps=[self._convert_step_row_to_dict(step) for step in steps_results],
            elements=[
                self._convert_element_row_to_dict(elem) for elem in elements_results
            ],
            tags=[],
        )

    async def update_thread(
        self,
        thread_id: str,
        name: Optional[str] = None,
        user_id: Optional[str] = None,
        metadata: Optional[Dict] = None,
        tags: Optional[List[str]] = None,
    ):
        if self.show_logger:
            logger.info(f"asyncpg: update_thread, thread_id={thread_id}")

        thread_name = self._truncate(
            name
            if name is not None
            else (metadata.get("name") if metadata and "name" in metadata else None)
        )

        # Convert UUID user_id to internal SERIAL ID for database storage
        internal_user_id = None
        if user_id:
            try:
                # Try to parse as UUID - if successful, convert to internal ID
                import uuid as uuid_module
                uuid_module.UUID(user_id)  # Validate UUID format
                # Query to get internal SERIAL ID from UUID
                user_query = """SELECT id FROM "User" WHERE user_uuid = $1"""
                user_result = await self.execute_query(user_query, {"user_uuid": user_id})
                if user_result:
                    internal_user_id = user_result[0]["id"]
            except (ValueError, TypeError):
                # If not a valid UUID, assume it's already an internal ID (legacy)
                internal_user_id = user_id

        data = {
            "id": thread_id,
            "name": thread_name,
            "user_id": internal_user_id,
            "tags": tags,
            "metadata": json.dumps(metadata) if metadata is not None else None,
        }

        # Remove None values
        data = {k: v for k, v in data.items() if v is not None}

        # Build the query dynamically based on available fields
        columns = [f'"{k}"' for k in data.keys()]
        placeholders = [f"${i + 1}" for i in range(len(data))]
        values = list(data.values())

        update_sets = [f'"{k}" = EXCLUDED."{k}"' for k in data.keys() if k != "id"]

        query = f"""
            INSERT INTO threads ({", ".join(columns)})
            VALUES ({", ".join(placeholders)})
            ON CONFLICT (id) DO UPDATE
            SET {", ".join(update_sets)};
        """

        await self.execute_query(query, {str(i + 1): v for i, v in enumerate(values)})

    def _extract_feedback_dict_from_step_row(self, row: Dict) -> Optional[FeedbackDict]:
        if row["feedback_id"] is not None:
            return FeedbackDict(
                forId=str(row["id"]),
                id=str(row["feedback_id"]),
                value=row["feedback_value"],
                comment=row["feedback_comment"],
            )
        return None

    def _convert_step_row_to_dict(self, row: Dict) -> StepDict:
        return StepDict(
            id=str(row["id"]),
            threadId=str(row["thread_id"]) if row.get("thread_id") else "",
            parentId=str(row["parent_id"]) if row.get("parent_id") else None,
            name=str(row.get("name")),
            type=row["type"],
            input=row.get("input", {}),
            output=row.get("output", {}),
            metadata=json.loads(row.get("metadata", "{}")),
            createdAt=row["created_at"].isoformat() if row.get("created_at") else None,
            start=row["start_time"].isoformat() if row.get("start_time") else None,
            showInput=row.get("show_input"),
            isError=row.get("is_error"),
            end=row["end_time"].isoformat() if row.get("end_time") else None,
            feedback=self._extract_feedback_dict_from_step_row(row),
        )

    def _convert_element_row_to_dict(self, row: Dict) -> ElementDict:
        metadata = json.loads(row.get("metadata", "{}"))
        return ElementDict(
            id=str(row["id"]),
            threadId=str(row["thread_id"]) if row.get("thread_id") else None,
            type=metadata.get("type", "file"),
            url=row["url"],
            name=row["name"],
            mime=row["mime_type"],
            objectKey=row["object_key"],
            forId=str(row["step_id"]),
            chainlitKey=row.get("chainlit_key"),
            display=row["display"],
            size=row["size_bytes"],
            language=row["language"],
            page=row["page_number"],
            autoPlay=row.get("autoPlay"),
            playerConfig=row.get("playerConfig"),
            props=json.loads(row.get("props") or "{}"),
        )

    async def build_debug_url(self) -> str:
        return ""

    async def cleanup(self):
        """Cleanup database connections"""
        if self.pool:
            await self.pool.close()

    def _truncate(self, text: Optional[str], max_length: int = 255) -> Optional[str]:
        return None if text is None else text[:max_length]
    
    # Helper methods for Hybrid ID Strategy (UUID + SERIAL)
    async def get_user_internal_id(self, user_uuid: str) -> Optional[int]:
        """Convert user UUID to internal SERIAL ID for performance-critical operations"""
        query = """SELECT id FROM "User" WHERE user_uuid = $1"""
        result = await self.execute_query(query, {"user_uuid": user_uuid})
        return result[0]["id"] if result else None
    
    async def get_user_uuid(self, internal_id: int) -> Optional[str]:
        """Convert internal SERIAL ID to user UUID for external APIs"""
        query = """SELECT user_uuid FROM "User" WHERE id = $1"""
        result = await self.execute_query(query, {"id": internal_id})
        return str(result[0]["user_uuid"]) if result else None
    
    async def get_user_by_uuid(self, user_uuid: str) -> Optional[Dict[str, Any]]:
        """Get user details by UUID (for external API queries)"""
        query = """
        SELECT id, user_uuid, username, identifier, email, role, is_active, is_verified,
               first_name, last_name, created_at, metadata
        FROM "User" 
        WHERE user_uuid = $1 AND is_active = TRUE
        """
        result = await self.execute_query(query, {"user_uuid": user_uuid})
        return dict(result[0]) if result else None
        
    # Custom AgentFusion methods below
    async def hash_password(self, password: str) -> str:
        """Hash password using bcrypt"""
        salt = bcrypt.gensalt()
        hashed = bcrypt.hashpw(password.encode('utf-8'), salt)
        return hashed.decode('utf-8')
    
    def verify_password(self, password: str, hashed: str) -> bool:
        """Verify password against hash"""
        return bcrypt.checkpw(password.encode('utf-8'), hashed.encode('utf-8'))
    
    async def authenticate_user(self, username: str, password: str, ip_address: str = None) -> Optional[Dict[str, Any]]:
        """
        Authenticate user with database lookup and security checks
        """
        # Ensure we have a connection pool
        await self.connect()
        
        async with self.pool.acquire() as conn:
            try:
                # First, check if user exists and get their details
                user_query = """
                    SELECT id, user_uuid, username, email, password_hash, role, is_active, is_verified, 
                           failed_login_attempts, locked_until, last_login, 
                           created_at
                    FROM "User" 
                    WHERE username = $1 OR email = $1
                """
                user_record = await conn.fetchrow(user_query, username)
                
                if not user_record:
                    # Log failed login attempt for non-existent user
                    await self.log_activity(conn, None, "login_failed", details={
                        "reason": "user_not_found",
                        "username": username,
                        "ip_address": ip_address
                    })
                    return None
                
                # Check if account is locked
                if user_record['locked_until'] and user_record['locked_until'] > datetime.utcnow():
                    await self.log_activity(conn, user_record['id'], "login_failed", details={
                        "reason": "account_locked",
                        "username": username,
                        "ip_address": ip_address,
                        "locked_until": user_record['locked_until'].isoformat()
                    })
                    return None
                
                # Check if account is active
                if not user_record['is_active']:
                    await self.log_activity(conn, user_record['id'], "login_failed", details={
                        "reason": "account_inactive",
                        "username": username,
                        "ip_address": ip_address
                    })
                    return None
                
                # Verify password
                if not self.verify_password(password, user_record['password_hash']):
                    # Record failed login attempt
                    await self.record_failed_login(conn, username)
                    await self.log_activity(conn, user_record['id'], "login_failed", details={
                        "reason": "invalid_password",
                        "username": username,
                        "ip_address": ip_address
                    })
                    return None
                
                # Password is correct - reset failed attempts and update last login
                update_query = """
                    UPDATE "User" 
                    SET last_login = CURRENT_TIMESTAMP, 
                        failed_login_attempts = 0,
                        locked_until = NULL
                    WHERE id = $1
                """
                await conn.execute(update_query, user_record['id'])
                
                # Log successful login
                await self.log_activity(conn, user_record['id'], "login_success", details={
                    "username": username,
                    "ip_address": ip_address,
                    "last_login": user_record['last_login'].isoformat() if user_record['last_login'] else None
                })
                
                return {
                    "id": user_record['id'],
                    "uuid": str(user_record['user_uuid']),
                    "username": user_record['username'],
                    "email": user_record['email'],
                    "role": user_record['role'],
                    "is_active": user_record['is_active'],
                    "is_verified": user_record['is_verified'],
                    "created_at": user_record['created_at'].isoformat()
                }
                
            except Exception as e:
                # Log authentication error
                await self.log_activity(conn, None, "login_error", details={
                    "error": str(e),
                    "username": username,
                    "ip_address": ip_address
                })
                raise e
    
    async def record_failed_login(self, conn, username: str):
        """Record failed login attempt and handle account locking"""
        lock_query = """
            UPDATE "User" 
            SET failed_login_attempts = failed_login_attempts + 1,
                locked_until = CASE 
                    WHEN failed_login_attempts >= 4 THEN CURRENT_TIMESTAMP + INTERVAL '30 minutes'
                    ELSE locked_until
                END
            WHERE username = $1 AND is_active = TRUE
        """
        await conn.execute(lock_query, username)
    
    async def log_activity(self, conn, user_id: Optional[int], activity_type: str, 
                          details: Dict[str, Any], status: str = "success"):
        """Log user activity"""
        log_query = """
            INSERT INTO user_activity_logs (
                user_id, activity_type, action_details, ip_address, status
            ) VALUES ($1, $2, $3, $4, $5)
        """
        await conn.execute(
            log_query, 
            user_id, 
            activity_type, 
            json.dumps(details),  # Serialize dictionary to JSON string
            details.get('ip_address'),
            status
        )
    
    async def update_user(self, user: PersistedUser) -> Optional[AgentFusionUser]:
        """Update user's last_login timestamp"""
        if not self.pool:
            await self.connect()
        
        async with self.pool.acquire() as conn:
            update_query = """
                UPDATE "User"
                SET last_login = CURRENT_TIMESTAMP,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = $1
            """
            await conn.execute(update_query, user.id)
        return user
    
    async def create_user(self, user: User) -> Optional[AgentFusionUser]:
        """
        When it reach here, it means that the user must be exists
        thereis two cases:
        1. user is authenticated by oauth, we should create a new user if it doesn't exist
        2. user is authenticated by password, we should fetch the user, 
           and it should never create a new user, because it already checked 
           from password_auth_callback and is exists in db
        """
        _user: Optional[PersistedUser] = await self.get_user(identifier=user.identifier)
        if _user:
            #if user is authenticated by password, it should never create a new user, 
            #and if the user is created from the last oauth, 
            #it should update the user's last_login timestamp
            await self.update_user(user)
            return _user            

        async with self.pool.acquire() as connection:
            try:
                now = await self.get_current_timestamp()
                
                # Extract user metadata
                metadata = user.metadata if hasattr(user, 'metadata') else {}
                
                # Handle nested metadata structure - extract email from nested metadata if present
                email = None
                if 'email' in metadata:
                    email = metadata['email']
                elif 'metadata' in metadata and isinstance(metadata['metadata'], dict):
                    email = metadata['metadata'].get('email')
                
                # Provide default email if still None to satisfy NOT NULL constraint
                if email is None:
                    email = f"{user.identifier}@example.com"  # Default email based on identifier
                
                # INSERT ... ON CONFLICT DO UPDATE query
                upsert_query = """
                INSERT INTO "User" (
                    id, user_uuid, username, identifier, email, role, first_name, last_name,
                    created_at, last_login, metadata, is_active
                ) VALUES (
                    $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12
                )
                ON CONFLICT (id) DO UPDATE SET
                    last_login = EXCLUDED.last_login
                RETURNING id, user_uuid, username, identifier, email, role, first_name, last_name, 
                        created_at, updated_at, metadata, is_active
                """
                
                params = [
                    user.id,  # id
                    user.uuid or str(uuid.uuid4()),  # user_uuid
                    user.identifier,  # username
                    user.identifier,  # identifier
                    metadata.get('email'),  # email
                    metadata.get('role', 'user'),  # role
                    metadata.get('first_name'),  # first_name
                    metadata.get('last_name'),  # last_name
                    now,  # created_at
                    now,  # last_login
                    json.dumps(metadata),  # metadata
                    True,  # is_active
                ]
                
                result = await connection.fetchrow(upsert_query, *params)
                
                if result:
                    # Convert database result to AgentFusionUser
                    result_metadata = json.loads(result.get('metadata', '{}'))
                    
                    return AgentFusionUser(
                        id=result['id'],
                        uuid=str(result['user_uuid']),
                        identifier=result['identifier'],
                        display_name=user.display_name or result.get('first_name') or result['identifier'],
                        email=result.get('email'),
                        role=result.get('role', 'user'),
                        first_name=result.get('first_name'),
                        last_name=result.get('last_name'),
                        createdAt=result['created_at'].isoformat(),
                        **{k: v for k, v in result_metadata.items() 
                        if k not in ['email', 'role', 'first_name', 'last_name']}
                    )
                
                return None
                
            except Exception as e:
                logger.error(f"Error in create_user: {e}")
                raise        
    
