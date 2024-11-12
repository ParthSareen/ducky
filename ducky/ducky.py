import argparse
import asyncio
from typing import Optional
from ollama import AsyncClient


class RubberDuck:
    def __init__(self, model: str = "codellama") -> None:
        self.system_prompt = """You are a pair progamming tool to help developers debug, think through design, and write code. 
        Help the user think through their approach and provide feedback on the code. Think step by step and ask clarifying questions if needed."""
        self.client = AsyncClient()
        self.model = model

    async def call_llama(self, code: str = "", prompt: Optional[str] = None, chain: bool = False) -> None:
        if prompt is None:
            user_prompt = input("\nEnter your prompt (or press Enter for default review): ")
            if not user_prompt:
                prompt = "review the code, find any issues if any, suggest cleanups if any:" + code
            else:
                prompt = user_prompt + code
        else:
            prompt = prompt + code

        responses = []
        while True:
            # Include previous responses in the prompt for context
            context_prompt = "\n".join(responses) + "\n" + prompt
            response = await self.client.generate(model=self.model, prompt=context_prompt)
            print(response['response'])
            responses.append(response['response'])
            if not chain:
                break
            prompt = input("\nAny questions? \n")


def read_files_from_dir(directory: str) -> str:
    import os

    files = os.listdir(directory)
    code = ""
    for file in files:
        code += open(directory + "/" + file).read()
    return code


async def ducky() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("question", nargs="*", help="Direct question to ask", default=None)
    parser.add_argument("--prompt", "-p", help="Custom prompt to be used", default=None)
    parser.add_argument("--file", "-f", help="The file to be processed", default=None)
    parser.add_argument("--directory", "-d", help="The directory to be processed", default=None)
    parser.add_argument(
        "--chain",
        "-c",
        help="Chain the output of the previous command to the next command",
        action="store_true",
        default=False,
    )
    parser.add_argument(
        "--model", "-m", help="The model to be used", default="codellama"
    )
    args, _ = parser.parse_known_args()

    # My testing has shown that the codellama:7b-python is good for returning python code from the program.
    # My intention with this tool was to give more general feedback and have back a back and forth with the user.
    rubber_ducky = RubberDuck(model=args.model)

    # Handle direct question from CLI
    if args.question is not None:
        question = " ".join(args.question)
        await rubber_ducky.call_llama(prompt=question, chain=args.chain)
        return

    if args.file is None and args.directory is None:
        # Handle interactive mode (no file/directory specified)
        await rubber_ducky.call_llama(prompt=args.prompt, chain=args.chain)
        if args.chain:
            while True:
                await rubber_ducky.call_llama(prompt=args.prompt, chain=args.chain)
        return

    # Handle file input
    if args.file is not None:
        code = open(args.file).read()
    # Handle directory input
    else:
        code = read_files_from_dir(args.directory)
        
    await rubber_ducky.call_llama(code=code, prompt=args.prompt, chain=args.chain)


def main():
    asyncio.run(ducky())

if __name__ == "__main__":
    main()
