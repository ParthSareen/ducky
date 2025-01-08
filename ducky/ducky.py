import argparse
import asyncio
from typing import Optional
from ollama import AsyncClient


class RubberDuck:
    def __init__(self, model: str = "qwen2.5-coder") -> None:
        self.system_prompt = """You are a pair progamming tool called Ducky or RubberDucky to help developers debug, think through design, and write code. 
        Help the user think through their approach and provide feedback on the code. Think step by step and ask clarifying questions if needed.
        If asked """
        self.client = AsyncClient()
        self.model = model

    async def call_llm(self, code: str = "", prompt: Optional[str] = None) -> None:
        chain = True if prompt is None else False
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
            stream = await self.client.generate(model=self.model, prompt=context_prompt, stream=True)
            response_text = ""
            async for chunk in stream:
                if 'response' in chunk:
                    print(chunk['response'], end='', flush=True)
                    response_text += chunk['response']
            print()  # New line after response completes
            responses.append(response_text)
            if not chain:
                break
            prompt = input("\n>> \n")


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
        "--model", "-m", help="The model to be used", default="qwen2.5-coder"
    )
    args, _ = parser.parse_known_args()

    rubber_ducky = RubberDuck(model=args.model)

    # Handle direct question from CLI
    if args.question:
        question = " ".join(args.question) 
        await rubber_ducky.call_llm(prompt=question)
        return

    # Handle interactive mode (no file/directory specified)
    if args.file is None and args.directory is None:
        await rubber_ducky.call_llm(prompt=args.prompt)
        if args.chain:
            while True:
                await rubber_ducky.call_llm(prompt=args.prompt)
        return

    # Get code from file or directory
    code = (open(args.file).read() if args.file 
            else read_files_from_dir(args.directory))

    await rubber_ducky.call_llm(code=code, prompt=args.prompt)


def main():
    asyncio.run(ducky())

if __name__ == "__main__":
    main()
