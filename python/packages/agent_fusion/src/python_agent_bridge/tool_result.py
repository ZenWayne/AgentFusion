import os
import tempfile
import logging
import json

def save_tool_result(tool_result_dir, agent_session_id: str, tool_result: str) -> None:
    """Save the result of a tool to a file. save to folder under temperory folder

    Args:
        tool_result_dir: The directory to save the tool result to
        tool_name: The name of the tool that generated the result
        tool_result: The result/content from the tool execution
        agent_session_id: The session ID for the agent (used as file prefix)

    Raises:
        OSError: If unable to create directory or write file
        IOError: If unable to write to the file
    """
    tool_results_dir = os.path.join(tool_result_dir, "tool_results", agent_session_id)

    # Ensure tool_results directory exists
    try:
        os.makedirs(tool_results_dir, exist_ok=True)
    except OSError as e:
        raise OSError(f"Unable to create tool_results directory: {e}")

    # Get next file index for this session
    try:
        existing_files = os.listdir(tool_results_dir)
        session_files = [f for f in existing_files if f.startswith(f"{agent_session_id}_") and f.endswith('.txt')]
        num_files = len(session_files)
    except OSError as e:
        raise OSError(f"Unable to access tool_results directory: {e}")

    # Create filename with metadata
    filename = f"{num_files}.txt"
    tool_result_file = os.path.join(tool_results_dir, filename)

    logging.info(f"Saving tool result to {tool_result_file}")
    # Write only the tool result content
    try:
        tool_result=json.loads(tool_result)
        call_result=tool_result[0].get("text")
        with open(tool_result_file, 'w', encoding='utf-8') as f:
            f.write(call_result)
    except IOError as e:
        raise IOError(f"Unable to write tool result to file {tool_result_file}: {e}")


def get_tool_result(index: int) -> str:
    """Get the result of a tool from a file. read from folder under temperory folder

    Args:
        index: The index of the file to read (relative to agent session)

    Returns:
        The content of the tool result file

    Raises:
        ValueError: If index is out of range
        OSError: If unable to access the tool_results directory
        IOError: If unable to read the file
    """
    # Get agent session ID from environment variable
    tool_results_dir = os.getenv('TOOL_RESULTS_DIR')
    agent_session_id = os.getenv('AGENT_SESSION_ID')

    if not agent_session_id:
        raise ValueError("AGENT_SESSION_ID environment variable is not set")

    tool_results_dir = os.path.join(tool_results_dir, "tool_results", agent_session_id)

    # Get files for this session
    try:
        existing_files = os.listdir(tool_results_dir)
        if index >= len(existing_files):
            raise ValueError(f"Index {index} out of range. Only {len(existing_files)} files found for session {agent_session_id}")
        real_index = len(existing_files) - index - 1
        file_path = os.path.join(tool_results_dir, f"{real_index}.txt")

    except OSError as e:
        raise OSError(f"Unable to access tool_results directory: {e}")

    # Read the file
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        return json.loads(content)
    except IOError as e:
        raise IOError(f"Unable to read tool result file {file_path}: {e}")