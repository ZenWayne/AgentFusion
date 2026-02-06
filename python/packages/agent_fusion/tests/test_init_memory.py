import asyncio
import unittest
from unittest.mock import MagicMock, AsyncMock
from autogen_core.models import UserMessage, SystemMessage, CreateResult
from agent_memory.context import MemoryContext

class TestMemoryContext(unittest.TestCase):
    def setUp(self):
        self.mock_data_layer = MagicMock()
        self.mock_data_layer.memory = MagicMock()
        self.mock_model_client = MagicMock()
        self.context = MemoryContext(
            data_layer=self.mock_data_layer,
            model_client=self.mock_model_client
        )

    def test_init_memory_no_queries(self):
        async def run_test():
            # Mock LLM response for no queries
            self.mock_model_client.create = AsyncMock(return_value=CreateResult(content='{"queries": []}', finish_reason="stop", usage={"prompt_tokens": 0, "completion_tokens": 0}, cached=False))
            
            message = UserMessage(content="Hello", source="user")
            result = await self.context.init_memory(message)
            
            self.assertEqual(len(result), 1)
            self.assertEqual(result[0], message)
        
        asyncio.run(run_test())

    def test_init_memory_with_memories(self):
        async def run_test():
            # Mock LLM response
            self.mock_model_client.create = AsyncMock(return_value=CreateResult(content='{"queries": ["test query"]}', finish_reason="stop", usage={"prompt_tokens": 0, "completion_tokens": 0}, cached=False))
            
            # Mock Memory Search
            mock_memory = MagicMock()
            mock_memory.memory_key = "key1"
            mock_memory.summary = "Test Summary"
            mock_memory.content = "Test Content"
            self.mock_data_layer.memory.search_memories = AsyncMock(return_value=[mock_memory])
            
            message = UserMessage(content="Help me with test", source="user")
            result = await self.context.init_memory(message)
            
            self.assertEqual(len(result), 2)
            self.assertIsInstance(result[0], SystemMessage)
            self.assertIn("Relevant Past Memories", result[0].content)
            self.assertIn("key1", result[0].content)
            self.assertEqual(result[1], message)

        asyncio.run(run_test())

if __name__ == "__main__":
    unittest.main()
