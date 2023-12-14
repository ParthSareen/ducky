import argparse
from typing import Optional
from langchain.llms.ollama import Ollama
from langchain.document_loaders import ObsidianLoader 
from langchain.embeddings import OllamaEmbeddings
from langchain.schema import StrOutputParser
from langchain.schema.runnable import RunnablePassthrough
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain.vectorstores import chroma
from langchain.chains.question_answering import load_qa_chain
from langchain.chains import RetrievalQA
from langchain.callbacks.streaming_stdout import StreamingStdOutCallbackHandler
# from transformers import LlamaForCausalLM, CodeLlamaTokenizer


def call_llama(code: str, prompt: Optional[str] = None):
    if prompt is None:
        prompt = "review the code, find any issues if any, suggest cleanups if any:" + code
    else:
        prompt = prompt + code
    system_prompt = "You are a pair progamming tool to help developers debug, think through design, and write code. Help the user rubber duck by providing feedback on the code."

    # TODO: find out how to enable the python trained model
    llm = Ollama(model="codellama", callbacks=[StreamingStdOutCallbackHandler()], system=system_prompt)

    # TODO: add chaining if it makes sense
    llm(prompt)

def ducky():
    parser = argparse.ArgumentParser()
    parser.add_argument("--prompt", help="Custom prompt to be used", default=None)
    parser.add_argument("--file", help="The file to be processed", default=None)
    parser.add_argument("--directory", help="The directory to be processed", default=None)
    args = parser.parse_known_args()

    if args.file is not None:
        code = open(args.file).read()
        call_llama(code=code, prompt=args.prompt)

if __name__ == "__main__":
    ducky()