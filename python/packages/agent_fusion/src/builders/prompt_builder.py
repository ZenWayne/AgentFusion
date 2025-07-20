import os
from os.path import join


class PromptBuilder:
    """Prompt builder following ModelBuilder pattern"""
    
    def __init__(self, prompt_path: str = "prompt"):
        self.prompt_path = prompt_path
    
    def get_prompt_by_catagory_and_name(self, agent_path: str, spliter: str = '/') -> str:
        """
        Get prompt content by category and name.
        
        Args:
            agent_path: Path to the agent (category/name format)
            spliter: Path separator, defaults to '/'
            
        Returns:
            str: Prompt content
            
        Raises:
            FileNotFoundError: If prompt file not found
        """
        paths = agent_path.split(spliter)

        dir = self.prompt_path

        for path in paths[:-1]:
            dir = join(dir, path)
        agent_name = paths[-1]
        prompt_file_path = join(
            dir, f"{agent_name}"
        )

        try:
            with open(prompt_file_path, "r", encoding="utf-8") as f:
                prompt_template = f.read()
        except:
            raise FileNotFoundError(f"prompt not found {prompt_file_path}")
        
        return prompt_template