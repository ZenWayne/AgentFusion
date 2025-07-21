import os
from os.path import join
from schemas.component import ComponentType


class PromptBuilder:
    """Prompt builder following ModelBuilder pattern"""
    
    def __init__(self, prompt_path: str = "config/prompt"):
        self.prompt_path = prompt_path
    
    def get_prompt_by_catagory_and_name(self, component_type: ComponentType, component_name: str) -> str:
        """
        Get prompt content by category and name.
        
        Args:
            component_type: Component type
            component_name: Component name
            
        Returns:
            str: Prompt content
            
        Raises:
            FileNotFoundError: If prompt file not found
        """
        paths = [component_type.value, component_name]

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