
import argparse
import asyncio
from autogen_core import CancellationToken
from chainlit_web.users import User

#CR inherit User and then  override the input_func to get the message from the command line
class CommandLineUser(User):
    def input_func(self):
        async def wrap_input(prompt: str, token: CancellationToken) -> str:
            print("Please enter a message, or type 'END' to end the chat:")
            while True:
                message = input(prompt)
                if message != "END":
                    return message
                else:
                    print("Please enter a message, or type 'END' to end the chat:")
        return wrap_input

async def main():
    current_user = CommandLineUser()
    #CR achive the same effect as python -m cli.chat run component_name you can reference 
    #src/chainlit_web/users.py, src/chainlit_web/run.py and the reference code in src/chainlit_web/
    #you should create user first, and then use the user to start a chat
    parser = argparse.ArgumentParser(description="Start a chat with an agent.")
    parser.add_argument("message", help="The message to send to the agent.")
    parser.add_argument("component_name", help="The name of the component to run.")
    args = parser.parse_args()

    # Create a configuration for the language model
    config_list = [
        {
            "model": "gpt-4",
            "api_key": "YOUR_API_KEY"  # Replace with your actual API key
        }
    ]

    # Create the assistant agent
    assistant = AssistantAgent(
        name="assistant",
        llm_config={
            "config_list": config_list
        }
    )

    # Create the user proxy agent
    user_proxy = UserProxyAgent(
        name="user_proxy",
        code_execution_config={"work_dir": "coding"}
    )

    # Start the chat
    await user_proxy.a_initiate_chat(
        assistant,
        message=args.message
    )

if __name__ == "__main__":
    asyncio.run(main())
