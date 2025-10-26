# Tools package for AgentFusion

# in the following phrases
# a tool function means a function return a FunctionToolWithType like return lambda : lazy_tool_loader[read](read) in read.py
# a tool function must contains doc string like read, you can reference read.py for implementation
# a tool means the tool that the lambda return, a pure function, like read in the above sample
# lazy_tool_loader lambda means lambda : lazy_tool_loader[read](read)
# there is four features represented by four classes
# 1. retrieve content from files or database to the latest context
#   there is a base retrieve tool class for extented for filesystem or vector database
#   there are two tool functions, one is retrive (return a lazy_tool_loader lambda), for the current implementation, the are 
#   retrieve file content base on regex pattern from file system, and the other is retrieve text base on query text from vector database(currently would be chroma)

# 2. update the content to filesystem or vector database
# with regex to match the coresponding line and replace it with new content

# 3. delete the content from filesystem or vector database
#    delete the file from filesystem or the text from vector database

# 4. code execution tool input is code snippet executed by python -c "code snippet"

# Import all tool functions for easy access

from .retrieve import retrieve_filesystem_tool, retrieve_vector_db_tool
from .update import update_file_tool, update_vector_db_tool, upsert_vector_db_tool
from .delete import delete_file_tool, delete_vector_db_documents_tool, delete_vector_db_collection_tool
from .execute import execute_code_tool, execute_file_tool, execute_multiline_tool
#from .rerank import dashscope_rerank_documents_tool, dashscope_rerank_tools_tool

# Export all tool functions
__all__ = [
    
    # Retrieve tools
    'retrieve_filesystem_tool',
    'retrieve_vector_db_tool',
    
    # Update tools  
    'update_file_tool',
    'update_vector_db_tool',
    'upsert_vector_db_tool',
    
    # Delete tools
    'delete_file_tool',
    'delete_vector_db_documents_tool', 
    'delete_vector_db_collection_tool',
    
    # Code execution tools
    'execute_code_tool',
    'execute_file_tool',
    'execute_multiline_tool',
    
    # DashScope rerank tools
    #'dashscope_rerank_documents_tool',
    #'dashscope_rerank_tools_tool',
]