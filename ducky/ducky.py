import argparse
from typing import Optional
from langchain.llms.ollama import Ollama
from langchain.callbacks.streaming_stdout import StreamingStdOutCallbackHandler


def call_llama(code: str, prompt: Optional[str] = None) -> None:
    """
    This function calls the Ollama model to provide feedback on the given code.

    Args:
        code (str): The code to be reviewed.
        prompt (Optional[str], optional): Custom prompt to be used. Defaults to None.
    """
    if prompt is None:
        prompt = "review the code, find any issues if any, suggest cleanups if any:" + code
    else:
        prompt = prompt + code
    system_prompt = """You are a pair progamming tool to help developers debug, think through design, and write code. Help the user rubber duck by providing feedback on the code."""

    # TODO: find out how to enable the python trained model
    llm = Ollama(model="codellama", callbacks=[StreamingStdOutCallbackHandler()], system=system_prompt)

    # TODO: add chaining if it makes sense
    llm(prompt)

def ducky() -> None:
    """
    This function parses the command line arguments and calls the Ollama model.
    """
    parser = argparse.ArgumentParser()
    parser.add_argument("--prompt", help="Custom prompt to be used", default=None)
    parser.add_argument("--file", help="The file to be processed", default=None)
    parser.add_argument("--directory", help="The directory to be processed", default=None)
    args, _ = parser.parse_known_args()

    if args.file is not None:
        code = open(args.file).read()
        call_llama(code=code, prompt=args.prompt)
    else:
        raise Exception("No file provided")

if __name__ == "__main__":
    ducky()
