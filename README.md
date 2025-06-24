# AutoGen Components library
This repository is for building Agent or WorkFlow more efficent in development

## Quick Start
```bash
pip install -e .
```
write agent prompt under config/prompt
config agent or workflow in config/metadata.json
config test case in test_case.json

python -m test.main

```bash
pip install -e .
start autogen from python code
```
## autogen studio support
```bash
python -m autogenstudio.cli ui --port 8080 --appdir ./tmp/app
```
## export config for AutoGen Studio
add the following case in cases in test_case.json
```json
{
    "dump_file_system": {
        "name": "dump_file_system",
        "type": "dump",
        "model_client": ["deepseek-chat_DeepSeek"],
        "agents": ["file_system"],
        "group_chats": ["prompt_flow"],
        "output_path": "dumped_config"
    }
}
```



